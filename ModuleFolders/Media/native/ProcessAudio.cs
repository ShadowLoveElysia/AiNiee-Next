// Process-tree loopback bridge. stdout carries JSON metadata followed by mono PCM.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

[ComImport, Guid("1CB9AD4C-DBFA-4C32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioClient
{
    [PreserveSig] int Initialize(int mode, uint flags, long duration, long periodicity, ref WaveFormat format, IntPtr session);
    [PreserveSig] int GetBufferSize(out uint frames);
    [PreserveSig] int GetStreamLatency(out long latency);
    [PreserveSig] int GetCurrentPadding(out uint frames);
    [PreserveSig] int IsFormatSupported(int mode, IntPtr format, out IntPtr closest);
    [PreserveSig] int GetMixFormat(out IntPtr format);
    [PreserveSig] int GetDevicePeriod(out long normal, out long minimum);
    [PreserveSig] int Start();
    [PreserveSig] int Stop();
    [PreserveSig] int Reset();
    [PreserveSig] int SetEventHandle(IntPtr handle);
    [PreserveSig] int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
}

[ComImport, Guid("C8ADBD64-E71E-48A0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioCaptureClient
{
    [PreserveSig] int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong position, out ulong clock);
    [PreserveSig] int ReleaseBuffer(uint frames);
    [PreserveSig] int GetNextPacketSize(out uint frames);
}

[ComImport, Guid("72A22D78-CDE4-431D-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IActivateOperation
{
    [PreserveSig] int GetActivateResult(out int result, [MarshalAs(UnmanagedType.IUnknown)] out object client);
}

[Guid("41D949AB-9862-444A-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown), ComVisible(true)]
public interface IActivateHandler
{
    [PreserveSig] int ActivateCompleted(IActivateOperation operation);
}

[Guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown), ComVisible(true)]
public interface IAgileObject { }

[StructLayout(LayoutKind.Sequential, Pack = 2)]
struct WaveFormat
{
    public ushort tag, channels;
    public uint sampleRate, bytesPerSecond;
    public ushort alignment, bits, extra;
}

[StructLayout(LayoutKind.Explicit, Size = 24)]
struct ActivationVariant
{
    [FieldOffset(0)] public ushort type;
    [FieldOffset(8)] public uint size;
    [FieldOffset(16)] public IntPtr data;
}

[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public sealed class Activation : IActivateHandler, IAgileObject
{
    internal readonly ManualResetEvent Done = new ManualResetEvent(false);
    internal object Client;
    internal int Result;
    public int ActivateCompleted(IActivateOperation operation)
    {
        try
        {
            int status;
            Result = operation.GetActivateResult(out status, out Client);
            if (Result >= 0) Result = status;
        }
        catch (Exception error) { Result = Marshal.GetHRForException(error); }
        finally { Done.Set(); }
        return 0;
    }
}

static class ProcessAudio
{
    [DllImport("Mmdevapi.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    static extern int ActivateAudioInterfaceAsync(string path, ref Guid iid, ref ActivationVariant parameters,
                                                  IActivateHandler handler, out IActivateOperation operation);
    static volatile bool stopped;
    static string stage = "initialize";

    static void Check(int result)
    {
        if (result < 0) Marshal.ThrowExceptionForHR(result);
    }

    static string Json(string value)
    {
        StringBuilder output = new StringBuilder("\"");
        foreach (char ch in value)
        {
            if (ch == '\\' || ch == '"') output.Append('\\').Append(ch);
            else if (ch < 32) output.Append("\\u").Append(((int)ch).ToString("x4"));
            else output.Append(ch);
        }
        return output.Append('"').ToString();
    }

    static void ListApplications()
    {
        StringBuilder output = new StringBuilder("[");
        bool first = true;
        foreach (Process process in Process.GetProcesses())
        {
            using (process)
            {
                try
                {
                    if (process.MainWindowHandle == IntPtr.Zero || process.HasExited) continue;
                    if (!first) output.Append(',');
                    output.Append("{\"pid\":").Append(process.Id)
                          .Append(",\"name\":").Append(Json(process.ProcessName))
                          .Append(",\"started\":").Append(Json(process.StartTime.ToUniversalTime().Ticks.ToString())).Append('}');
                    first = false;
                }
                catch (Exception) { }
            }
        }
        Console.WriteLine(output.Append(']').ToString());
    }

    [MTAThread]
    static int Main(string[] arguments)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (arguments.Length == 1 && arguments[0] == "list") { ListApplications(); return 0; }
        IntPtr blob = IntPtr.Zero;
        IAudioClient client = null;
        object captureObject = null;
        IActivateOperation operation = null;
        Activation activation = new Activation();
        AutoResetEvent samplesReady = new AutoResetEvent(false);
        Process target = null;
        bool started = false;
        try
        {
            if (arguments.Length != 2 || IntPtr.Size != 8) throw new ArgumentException();
            target = Process.GetProcessById(int.Parse(arguments[0]));
            if (target.StartTime.ToUniversalTime().Ticks.ToString() != arguments[1]) throw new InvalidOperationException();
            blob = Marshal.AllocCoTaskMem(12);
            Marshal.WriteInt32(blob, 0, 1);
            Marshal.WriteInt32(blob, 4, target.Id);
            Marshal.WriteInt32(blob, 8, 0);
            ActivationVariant parameters = new ActivationVariant { type = 65, size = 12, data = blob };
            Guid clientId = typeof(IAudioClient).GUID;
            stage = "activate_process_loopback";
            Check(ActivateAudioInterfaceAsync("VAD\\Process_Loopback", ref clientId, ref parameters, activation, out operation));
            if (!activation.Done.WaitOne(10000)) throw new TimeoutException();
            Check(activation.Result);
            client = (IAudioClient)activation.Client;
            WaveFormat format = new WaveFormat { tag = 1, channels = 2, sampleRate = 16000,
                                                  bytesPerSecond = 64000, alignment = 4, bits = 16 };
            stage = "initialize_process_loopback";
            // WASAPI converts the process mix to stereo 16 kHz before mono downmix.
            Check(client.Initialize(0, 0x00020000 | 0x00040000 | 0x80000000 | 0x08000000, 0, 0, ref format, IntPtr.Zero));
            Check(client.SetEventHandle(samplesReady.SafeWaitHandle.DangerousGetHandle()));
            Guid captureId = typeof(IAudioCaptureClient).GUID;
            Check(client.GetService(ref captureId, out captureObject));
            IAudioCaptureClient capture = (IAudioCaptureClient)captureObject;
            Check(client.Start());
            started = true;
            Thread parent = new Thread(delegate() {
                try { Console.OpenStandardInput().ReadByte(); }
                finally { stopped = true; samplesReady.Set(); }
            });
            parent.IsBackground = true;
            parent.Start();
            Console.WriteLine("{\"sample_rate\":16000,\"channels\":1,\"format\":\"f32le\",\"backend\":\"wasapi-process\"}");
            Console.Out.Flush();
            using (BinaryWriter output = new BinaryWriter(Console.OpenStandardOutput()))
            {
                stage = "capture_process_loopback";
                while (!stopped)
                {
                    samplesReady.WaitOne(100);
                    if (stopped) break;
                    if (target.HasExited) { stage = "application_exited"; throw new InvalidOperationException(); }
                    uint available;
                    Check(capture.GetNextPacketSize(out available));
                    while (available > 0)
                    {
                        IntPtr data;
                        uint frames, flags;
                        ulong position, clock;
                        Check(capture.GetBuffer(out data, out frames, out flags, out position, out clock));
                        try
                        {
                            if (frames > 16000 * 2) throw new InvalidOperationException();
                            short[] pcm = new short[frames * 2];
                            if ((flags & 2) == 0) Marshal.Copy(data, pcm, 0, pcm.Length);
                            for (int i = 0; i < frames; i++) output.Write((pcm[i * 2] + pcm[i * 2 + 1]) / 65536.0f);
                        }
                        finally { Check(capture.ReleaseBuffer(frames)); }
                        output.Flush();
                        Check(capture.GetNextPacketSize(out available));
                    }
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("{\"stage\":" + Json(stage) + ",\"status\":" + Marshal.GetHRForException(error) + "}");
            return 1;
        }
        finally
        {
            stopped = true;
            if (started && client != null) client.Stop();
            if (captureObject != null) Marshal.ReleaseComObject(captureObject);
            if (client != null) Marshal.ReleaseComObject(client);
            if (operation != null) Marshal.ReleaseComObject(operation);
            if (blob != IntPtr.Zero) Marshal.FreeCoTaskMem(blob);
            if (target != null) target.Dispose();
            // Keep callback and event handles valid until process shutdown on activation timeout.
            GC.KeepAlive(activation);
            GC.KeepAlive(samplesReady);
        }
    }
}
