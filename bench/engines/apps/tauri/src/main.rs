use std::io::Write;
use tauri::http::Response;

fn pct_decode(s: &str) -> String {
    let b = s.as_bytes();
    let mut out = Vec::with_capacity(b.len());
    let mut i = 0;
    while i < b.len() {
        if b[i] == b'%' && i + 2 < b.len() {
            if let Ok(v) = u8::from_str_radix(&s[i + 1..i + 3], 16) { out.push(v); i += 3; continue; }
        }
        out.push(if b[i] == b'+' { b' ' } else { b[i] });
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn main() {
    let dir = std::path::PathBuf::from(std::env::var("BENCH_DIR").expect("BENCH_DIR"));
    let page = std::env::var("BENCH_PAGE").unwrap_or_else(|_| "bench.html".into());
    let (w, h) = (1280.0, 720.0);
    tauri::Builder::default()
        .register_uri_scheme_protocol("bench", move |_ctx, req| {
            let uri = req.uri();
            let path = uri.path();
            if path == "/__mark" {
                let msg = uri.query().and_then(|q| q.strip_prefix("msg=")).map(pct_decode).unwrap_or_default();
                let mut o = std::io::stdout().lock();
                let _ = writeln!(o, "{}", msg);
                let _ = o.flush();
                return Response::builder().status(204).body(Vec::new()).unwrap();
            }
            let rel = path.trim_start_matches('/');
            match std::fs::read(dir.join(rel)) {
                Ok(bytes) => {
                    let mime = if rel.ends_with(".html") { "text/html" } else if rel.ends_with(".js") { "text/javascript" }
                        else if rel.ends_with(".css") { "text/css" } else if rel.ends_with(".ttf") { "font/ttf" } else { "application/octet-stream" };
                    Response::builder().header("Content-Type", mime).body(bytes).unwrap()
                }
                Err(_) => Response::builder().status(404).body(Vec::new()).unwrap(),
            }
        })
        .setup(move |app| {
            let url = format!("bench://localhost/{}", page);
            tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::CustomProtocol(url.parse().unwrap()))
                .title("bench-tauri").inner_size(w, h)
                // As the Electron host: on top and unthrottled, since WebKit starves a covered window's frames.
                .always_on_top(true)
                .background_throttling(tauri::utils::config::BackgroundThrottlingPolicy::Disabled)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("tauri run");
}
