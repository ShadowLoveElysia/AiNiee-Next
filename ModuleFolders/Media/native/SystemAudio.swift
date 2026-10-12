// Native system-audio bridge. stdout carries a format header followed by PCM.
import Foundation
import AppKit
import AVFoundation
import CoreAudio
import ScreenCaptureKit
import CoreMedia
import Darwin

struct CaptureError: Error {
    let stage: String
    let status: Int32
}

func check(_ status: OSStatus, _ stage: String) throws {
    if status != noErr { throw CaptureError(stage: stage, status: status) }
}

func report(_ stage: String, _ status: Int32 = 0) {
    let data = try! JSONSerialization.data(withJSONObject: ["stage": stage, "status": status])
    FileHandle.standardError.write(data + Data([10]))
}

final class PCMSink {
    let queue = DispatchQueue(label: "ai.ainiee.system-audio.pcm")
    private let slots = DispatchSemaphore(value: 32)
    private var converter: AVAudioConverter?
    private var inputFormat: AVAudioFormat?
    private let outputFormat = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                             sampleRate: 16000, channels: 1, interleaved: false)!
    private var enabled = false
    var onFailure: ((Error) -> Void)?

    func begin(_ backend: String) {
        queue.sync {
            let header = try! JSONSerialization.data(withJSONObject: [
                "sample_rate": 16000, "channels": 1, "format": "f32le", "backend": backend
            ])
            FileHandle.standardOutput.write(header + Data([10]))
            enabled = true
        }
    }

    func end() { queue.sync { enabled = false } }

    func receive(_ source: AVAudioPCMBuffer) {
        guard source.frameLength > 0 else { return }
        // Own callback memory before returning to HAL; bound pending allocations.
        guard slots.wait(timeout: .now()) == .success else {
            onFailure?(CaptureError(stage: "audio_queue_overrun", status: 0))
            return
        }
        guard let copy = AVAudioPCMBuffer(pcmFormat: source.format, frameCapacity: source.frameLength) else {
            slots.signal()
            onFailure?(CaptureError(stage: "audio_buffer_allocation", status: 0))
            return
        }
        copy.frameLength = source.frameLength
        let original = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: source.audioBufferList))
        let destination = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        for index in 0..<original.count {
            guard let from = original[index].mData, let to = destination[index].mData else { continue }
            memcpy(to, from, Int(original[index].mDataByteSize))
        }
        queue.async { [self] in
            defer { slots.signal() }
            guard enabled else { return }
            do { try convert(copy) } catch { onFailure?(error) }
        }
    }

    private func convert(_ buffer: AVAudioPCMBuffer) throws {
        if inputFormat != buffer.format {
            converter = AVAudioConverter(from: buffer.format, to: outputFormat)
            inputFormat = buffer.format
        }
        guard let converter else { throw CaptureError(stage: "audio_converter", status: 0) }
        let capacity = AVAudioFrameCount(ceil(Double(buffer.frameLength) * 16000 / buffer.format.sampleRate) + 128)
        guard let output = AVAudioPCMBuffer(pcmFormat: outputFormat, frameCapacity: capacity) else {
            throw CaptureError(stage: "audio_buffer_allocation", status: 0)
        }
        var supplied = false
        var error: NSError?
        let status = converter.convert(to: output, error: &error) { _, state in
            if supplied { state.pointee = .noDataNow; return nil }
            supplied = true
            state.pointee = .haveData
            return buffer
        }
        if status == .error { throw CaptureError(stage: "audio_conversion", status: Int32(error?.code ?? -1)) }
        if output.frameLength > 0, let samples = output.floatChannelData {
            FileHandle.standardOutput.write(Data(bytes: samples[0], count: Int(output.frameLength) * 4))
        }
    }
}

@available(macOS 14.2, *)
final class ProcessTapCapture {
    private var tap: AudioObjectID = 0
    private var aggregate: AudioObjectID = 0
    private var io: AudioDeviceIOProcID?
    private let sink: PCMSink
    init(_ sink: PCMSink) { self.sink = sink }

    func start() throws {
        let description = CATapDescription(stereoGlobalTapButExcludeProcesses: [])
        description.uuid = UUID()
        description.name = "AiNiee System Audio"
        description.isPrivate = true
        description.muteBehavior = .unmuted
        try check(AudioHardwareCreateProcessTap(description, &tap), "create_process_tap")
        var format = AudioStreamBasicDescription()
        var address = AudioObjectPropertyAddress(mSelector: kAudioTapPropertyFormat,
                                                mScope: kAudioObjectPropertyScopeGlobal,
                                                mElement: kAudioObjectPropertyElementMain)
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        try check(AudioObjectGetPropertyData(tap, &address, 0, nil, &size, &format), "tap_format")
        guard let audioFormat = AVAudioFormat(streamDescription: &format) else {
            throw CaptureError(stage: "tap_audio_format", status: 0)
        }
        let config: [String: Any] = [
            kAudioAggregateDeviceNameKey: "AiNiee Private Audio Tap",
            kAudioAggregateDeviceUIDKey: UUID().uuidString,
            kAudioAggregateDeviceIsPrivateKey: true,
            kAudioAggregateDeviceIsStackedKey: false,
            kAudioAggregateDeviceTapAutoStartKey: true,
            kAudioAggregateDeviceTapListKey: [[
                kAudioSubTapUIDKey: description.uuid.uuidString,
                kAudioSubTapDriftCompensationKey: true
            ]]
        ]
        try check(AudioHardwareCreateAggregateDevice(config as CFDictionary, &aggregate), "create_aggregate")
        try check(AudioDeviceCreateIOProcIDWithBlock(&io, aggregate, nil) { [sink] _, input, _, _, _ in
            guard let buffer = AVAudioPCMBuffer(pcmFormat: audioFormat, bufferListNoCopy: input) else {
                sink.onFailure?(CaptureError(stage: "tap_audio_buffer", status: 0))
                return
            }
            sink.receive(buffer)
        }, "create_audio_io")
        try check(AudioDeviceStart(aggregate, io), "start_audio_permission")
        sink.begin("coreaudio-tap")
    }

    func stop() {
        if aggregate != 0 {
            if let io {
                AudioDeviceStop(aggregate, io)
                AudioDeviceDestroyIOProcID(aggregate, io)
            }
            AudioHardwareDestroyAggregateDevice(aggregate)
            aggregate = 0
            io = nil
        }
        if tap != 0 { AudioHardwareDestroyProcessTap(tap); tap = 0 }
    }
    deinit { stop() }
}

@available(macOS 13.0, *)
final class ScreenAudioCapture: NSObject, SCStreamOutput, SCStreamDelegate {
    private var stream: SCStream?
    private let sink: PCMSink
    private let callbackQueue = DispatchQueue(label: "ai.ainiee.system-audio.screen")
    init(_ sink: PCMSink) { self.sink = sink }

    func start() async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        guard let display = content.displays.first else { throw CaptureError(stage: "no_display", status: 0) }
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        let config = SCStreamConfiguration()
        config.capturesAudio = true
        config.excludesCurrentProcessAudio = true
        config.sampleRate = 16000
        config.channelCount = 1
        // Subscribe only to audio; no video frames are consumed or stored.
        config.width = 32
        config.height = 32
        config.minimumFrameInterval = CMTime(value: 1, timescale: 1)
        let capture = SCStream(filter: filter, configuration: config, delegate: self)
        stream = capture
        try capture.addStreamOutput(self, type: .audio, sampleHandlerQueue: callbackQueue)
        try await capture.startCapture()
        sink.begin("screencapturekit")
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio, sampleBuffer.isValid else { return }
        do {
            try sampleBuffer.withAudioBufferList { list, _ in
                guard var description = sampleBuffer.formatDescription?.audioStreamBasicDescription,
                      let format = AVAudioFormat(streamDescription: &description),
                      let buffer = AVAudioPCMBuffer(pcmFormat: format, bufferListNoCopy: list.unsafePointer) else {
                    throw CaptureError(stage: "screen_audio_buffer", status: 0)
                }
                sink.receive(buffer)
            }
        } catch { sink.onFailure?(error) }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) { sink.onFailure?(error) }
    func stop() async { try? await stream?.stopCapture(); stream = nil }
}

@available(macOS 13.0, *)
final class CaptureController {
    let sink = PCMSink()
    var tap: AnyObject?
    var screen: ScreenAudioCapture?
    private var stopping = false

    func start(_ requested: String) async {
        sink.onFailure = { error in
            DispatchQueue.main.async { Task { await self.finish(error) } }
        }
        do {
            if #available(macOS 14.2, *), requested != "screen" {
                let capture = ProcessTapCapture(sink)
                tap = capture
                try capture.start()
            } else {
                if requested == "tap" { throw CaptureError(stage: "requires_macos_14_2", status: 0) }
                let capture = ScreenAudioCapture(sink)
                screen = capture
                try await capture.start()
            }
        } catch { await finish(error) }
    }

    func finish(_ error: Error? = nil) async {
        guard !stopping else { return }
        stopping = true
        if let error = error as? CaptureError { report(error.stage, error.status) }
        else if let error { report("capture_permission_or_stream", Int32((error as NSError).code)) }
        if #available(macOS 14.2, *), let capture = tap as? ProcessTapCapture { capture.stop() }
        await screen?.stop()
        sink.end()
        exit(error == nil ? 0 : 1)
    }
}

if #available(macOS 13.0, *) {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let capture = CaptureController()
    let requested = CommandLine.arguments.dropFirst().first ?? "auto"
    var signals: [DispatchSourceSignal] = []
    for number in [SIGINT, SIGTERM, SIGHUP] {
        signal(number, SIG_IGN)
        let source = DispatchSource.makeSignalSource(signal: number, queue: .main)
        source.setEventHandler { Task { await capture.finish() } }
        source.resume()
        signals.append(source)
    }
    signal(SIGPIPE, SIG_IGN)
    DispatchQueue.global().async {
        while !FileHandle.standardInput.readData(ofLength: 1).isEmpty {}
        DispatchQueue.main.async { Task { await capture.finish() } }
    }
    Task { await capture.start(requested) }
    app.run()
} else {
    report("requires_macos_13")
    exit(1)
}
