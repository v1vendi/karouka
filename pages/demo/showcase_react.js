// The showcase page's "React" tab. Application code only -- it runs
// against the unmodified React 18.3.1 UMD development bundles vendored in
// tests/data/frameworks/react-counter/ (pinned by tools/vendor.py
// DIR_MANIFEST["react"]). Plain React.createElement, no JSX, so there is
// no build step for this file.
//
// Every position is absolute and every colour is fixed, because
// showcase_main.cpp asserts the scripted clicks' effects by reading pixels
// at known coordinates (see the kReact* constants there). Change a position
// or colour here and the matching constant must move with it.
(function () {
  const e = React.createElement;
  const useState = React.useState;
  const useEffect = React.useEffect;
  const useMemo = React.useMemo;

  // Palette a new task cycles through; the first four are the seed tasks'.
  const COLORS = [
    "rgb(230, 70, 70)", "rgb(80, 200, 120)", "rgb(70, 130, 220)",
    "rgb(160, 90, 220)", "rgb(240, 160, 40)", "rgb(40, 200, 210)",
  ];
  const SEED = [
    { id: 1, name: "Write spec", done: true, color: COLORS[0] },
    { id: 2, name: "Add tests", done: false, color: COLORS[1] },
    { id: 3, name: "Implement", done: false, color: COLORS[2] },
    { id: 4, name: "Measure", done: false, color: COLORS[3] },
  ];
  const ROW_TOP = 138, ROW_STEP = 30;
  const SORT_LABELS = ["Sort: none", "Sort: A-Z", "Sort: Z-A"];

  function pos(left, top, width, height, extra) {
    const s = { left: left + "px", top: top + "px" };
    if (width !== undefined) s.width = width + "px";
    if (height !== undefined) s.height = height + "px";
    return Object.assign(s, extra || {});
  }

  function Button(props) {
    return e("button", {
      id: props.id,
      className: "fw-btn" + (props.pressed ? " pressed" : ""),
      style: pos(props.left, props.top, props.width, 24),
      disabled: props.disabled,
      onClick: props.onClick,
    }, props.label);
  }

  // ---- Task list: filter, sort, add, remove, toggle done. -----------------
  function TaskList() {
    const [tasks, setTasks] = useState(SEED);
    const [draft, setDraft] = useState("Review");
    const [filter, setFilter] = useState("all");
    const [sort, setSort] = useState(0);
    const [nextId, setNextId] = useState(5);

    const visible = useMemo(function () {
      let list = tasks.filter(function (t) {
        return filter === "all" || (filter === "done" ? t.done : !t.done);
      });
      if (sort !== 0) {
        list = list.slice().sort(function (a, b) {
          const c = a.name < b.name ? -1 : a.name > b.name ? 1 : 0;
          return sort === 1 ? c : -c;
        });
      }
      return list;
    }, [tasks, filter, sort]);

    function add() {
      const name = draft.trim();
      if (!name || tasks.length >= 8) return;
      setTasks(tasks.concat([{ id: nextId, name: name, done: false,
                               color: COLORS[(nextId - 1) % COLORS.length] }]));
      setNextId(nextId + 1);
      setDraft("");
    }
    function remove(id) {
      setTasks(tasks.filter(function (t) { return t.id !== id; }));
    }
    function toggle(id) {
      setTasks(tasks.map(function (t) {
        return t.id === id ? Object.assign({}, t, { done: !t.done }) : t;
      }));
    }

    const open = tasks.filter(function (t) { return !t.done; }).length;
    return e("div", null,
      e("div", { className: "card fw-label", style: pos(16, 48, 448, 20) },
        "Task list: filter, sort, add, remove (useState/useMemo)"),
      e("input", {
        id: "reactDraft", className: "fw-input", type: "text", value: draft,
        style: pos(16, 74, 196, 24),
        onChange: function (ev) { setDraft(ev.target.value); },
        onKeyDown: function (ev) { if (ev.key === "Enter") add(); },
      }),
      e(Button, { id: "reactAdd", left: 220, top: 74, width: 60, label: "Add",
                  disabled: draft.trim() === "", onClick: add }),
      e(Button, { id: "reactSort", left: 288, top: 74, width: 104, label: SORT_LABELS[sort],
                  onClick: function () { setSort((sort + 1) % 3); } }),
      ["all", "open", "done"].map(function (f, i) {
        return e(Button, { key: f, id: "reactFilter-" + f, left: 16 + i * 72, top: 106,
                           width: 64, label: f, pressed: filter === f,
                           onClick: function () { setFilter(f); } });
      }),
      e("div", { className: "fw-note", style: pos(240, 108, 224, 20) },
        open + " open / " + tasks.length + " total"),
      visible.map(function (t, i) {
        return e("div", { key: t.id, className: "fw-row" + (t.done ? " done" : ""),
                          style: pos(16, ROW_TOP + i * ROW_STEP, 448, 26) },
          e("div", { className: "fw-swatch", style: pos(6, 5, 14, 14, { background: t.color }) }),
          e("div", { className: "fw-row-text", style: pos(28, 2, 300, 20),
                     onClick: function () { toggle(t.id); } },
            (t.done ? "[x] " : "[ ] ") + t.name),
          e("button", { className: "fw-btn fw-remove", style: pos(410, 2, 32, 20),
                        onClick: function () { remove(t.id); } }, "x"));
      }));
  }

  // ---- Controlled form with live validation. ------------------------------
  function SignupForm() {
    const [name, setName] = useState("");
    const [email, setEmail] = useState("");
    const [agree, setAgree] = useState(false);
    const [sent, setSent] = useState("");

    const nameOk = name.trim().length >= 3;
    const emailOk = /^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(email);
    const valid = nameOk && emailOk && agree;

    function field(id, label, top, value, set, ok, hint) {
      return e("div", null,
        e("div", { className: "fw-note", style: pos(496, top + 2, 60, 20) }, label),
        e("input", { id: id, className: "fw-input", type: "text", value: value,
                     style: pos(560, top, 200, 24),
                     onChange: function (ev) { set(ev.target.value); setSent(""); } }),
        e("div", { className: "fw-swatch" + (ok ? " ok" : " bad"), style: pos(768, top + 5, 14, 14) }),
        e("div", { className: "fw-note" + (ok ? "" : " bad"), style: pos(790, top + 2, 160, 20) },
          ok ? "looks good" : hint));
    }

    return e("form", { onSubmit: function (ev) { ev.preventDefault(); if (valid) setSent(name.trim()); } },
      e("div", { className: "card fw-label", style: pos(496, 48, 448, 20) },
        "Controlled form + validation"),
      field("reactName", "Name", 74, name, setName, nameOk, "3+ characters"),
      field("reactEmail", "Email", 104, email, setEmail, emailOk, "needs a@b.cc"),
      e("input", { id: "reactAgree", type: "checkbox", checked: agree, className: "fw-check",
                   style: pos(560, 138, 16, 16),
                   onChange: function (ev) { setAgree(ev.target.checked); } }),
      e("div", { className: "fw-note", style: pos(584, 136, 180, 20) }, "I agree to the terms"),
      e("button", { id: "reactSubmit", type: "submit", className: "fw-btn",
                    style: pos(560, 164, 100, 24), disabled: !valid }, "Sign up"),
      e("div", { className: "fw-note" + (sent ? " ok" : ""), style: pos(670, 166, 280, 20) },
        sent ? "Welcome, " + sent + "!" : valid ? "ready to submit" : "fill in every field"));
  }

  // ---- <select> bound to state. --------------------------------------------
  function ThemePicker() {
    const THEMES = {
      ocean: "rgb(40, 110, 200)", forest: "rgb(50, 150, 80)", sunset: "rgb(220, 110, 50)",
    };
    const [theme, setTheme] = useState("forest");
    return e("div", null,
      e("div", { className: "card fw-label", style: pos(496, 204, 448, 20) },
        "<select> bound to state"),
      e("select", { id: "reactTheme", className: "fw-select", value: theme,
                    style: pos(496, 230, 140, 24),
                    onChange: function (ev) { setTheme(ev.target.value); } },
        Object.keys(THEMES).map(function (k) { return e("option", { key: k, value: k }, k); })),
      e("div", { id: "reactThemeSwatch", className: "fw-swatch",
                 style: pos(648, 230, 60, 24, { background: THEMES[theme] }) }),
      e("div", { className: "fw-note", style: pos(716, 232, 220, 20) }, "theme: " + theme));
  }

  // ---- State-driven animation: a build pipeline stepping on a timer. -------
  function Pipeline() {
    const STAGES = ["lint", "build", "test", "ship"];
    const [running, setRunning] = useState(false);
    const [stage, setStage] = useState(-1);

    useEffect(function () {
      if (!running) return undefined;
      const id = setInterval(function () {
        setStage(function (s) { return Math.min(s + 1, STAGES.length - 1); });
      }, 300);
      return function () { clearInterval(id); };
    }, [running]);
    useEffect(function () {
      if (running && stage === STAGES.length - 1) setRunning(false);
    }, [running, stage]);

    return e("div", null,
      e("div", { className: "card fw-label", style: pos(496, 270, 448, 20) },
        "useEffect timer + CSS transitions"),
      e(Button, { id: "reactRun", left: 496, top: 296, width: 100,
                  label: running ? "Running" : "Run", disabled: running,
                  onClick: function () { setStage(0); setRunning(true); } }),
      STAGES.map(function (name, i) {
        return e("div", { key: name,
                          className: "fw-stage" + (i < stage || (i === stage && !running) ? " passed"
                                                   : i === stage ? " active" : ""),
                          style: pos(608 + i * 84, 296, 76, 24) }, name);
      }),
      e("div", { className: "fw-track", style: pos(496, 330, 444, 10) },
        e("div", { id: "reactProgress", className: "fw-fill",
                   style: pos(0, 0, Math.round(444 * (stage + 1) / STAGES.length), 10) })));
  }

  function App() {
    return e("div", { id: "reactApp" },
      e(TaskList), e(SignupForm), e(ThemePicker), e(Pipeline));
  }

  ReactDOM.createRoot(document.getElementById("reactRoot")).render(e(App));
})();
