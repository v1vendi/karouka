// Appends the bench page's marker lines to $BENCH_MARK_FILE (stdout is buffered and lost on kill),
// and keeps the window on top: WebKit starves a covered window's frames.
const enc = new TextEncoder();
export const api = {
  async mark({ line }) {
    const path = tjs.env.BENCH_MARK_FILE;
    if (!path) { console.log(line); return; }
    const f = await tjs.open(path, 'a');
    await f.write(enc.encode(line + '\n'));
    await f.close();
  },
};

export function init(app) {
  app.setAlwaysOnTop(true);
}
