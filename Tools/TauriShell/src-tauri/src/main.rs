#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

struct BackendState {
    child: Mutex<Option<Child>>,
}

impl Default for BackendState {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
        }
    }
}

fn io_error(message: impl Into<String>) -> std::io::Error {
    std::io::Error::new(std::io::ErrorKind::Other, message.into())
}

fn parse_port() -> u16 {
    std::env::var("AINIEE_GUI_PORT")
        .ok()
        .and_then(|v| v.parse::<u16>().ok())
        .unwrap_or(18000)
}

fn resolve_shell_dir() -> Result<PathBuf, String> {
    let shell_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("Failed to resolve shell directory.")?
        .to_path_buf();

    let host_script = shell_dir.join("tauri_web_host.py");
    if !host_script.exists() {
        return Err(format!("Missing host script: {}", host_script.display()));
    }

    Ok(shell_dir)
}

fn spawn_backend(shell_dir: &Path, port: u16) -> Result<Child, String> {
    let host_script = shell_dir.join("tauri_web_host.py");
    let port_arg = port.to_string();

    let mut uv_cmd = Command::new("uv");
    uv_cmd
        .arg("run")
        .arg(&host_script)
        .arg("--port")
        .arg(&port_arg)
        .current_dir(shell_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    match uv_cmd.spawn() {
        Ok(child) => Ok(child),
        Err(uv_err) => {
            let mut py_cmd = Command::new("python");
            py_cmd
                .arg(&host_script)
                .arg("--port")
                .arg(&port_arg)
                .current_dir(shell_dir)
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());

            py_cmd
                .spawn()
                .map_err(|py_err| format!("Failed to start backend. uv error: {uv_err}; python error: {py_err}"))
        }
    }
}

fn wait_for_backend(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn stop_backend(app_handle: &tauri::AppHandle) {
    let state = app_handle.state::<BackendState>();
    let mut child_slot = match state.child.lock() {
        Ok(guard) => guard,
        Err(_) => return,
    };

    if let Some(child) = child_slot.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *child_slot = None;
}

fn main() {
    tauri::Builder::default()
        .manage(BackendState::default())
        .setup(|app| {
            let port = parse_port();
            let shell_dir = resolve_shell_dir().map_err(io_error)?;
            let mut child = spawn_backend(&shell_dir, port).map_err(io_error)?;

            if !wait_for_backend(port, Duration::from_secs(20)) {
                let _ = child.kill();
                let _ = child.wait();
                return Err(io_error(format!(
                    "Backend did not become ready at http://127.0.0.1:{port} within timeout."
                ))
                .into());
            }

            {
                let state = app.state::<BackendState>();
                let mut child_slot = state
                    .child
                    .lock()
                    .map_err(|_| io_error("Failed to lock backend child state"))?;
                *child_slot = Some(child);
            }

            let target_url = format!("http://127.0.0.1:{port}");
            let url = target_url
                .parse()
                .map_err(|e| io_error(format!("Invalid URL {target_url}: {e}")))?;

            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("AiNiee GUI (Tauri PoC)")
                .inner_size(1280.0, 860.0)
                .min_inner_size(1024.0, 680.0)
                .build()
                .map_err(|e| io_error(format!("Failed to create window: {e}")))?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                stop_backend(app_handle);
            }
            _ => {}
        });
}
