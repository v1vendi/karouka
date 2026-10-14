(() => {
  var __defProp = Object.defineProperty;
  var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
  var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);

  // node_modules/svelte/src/runtime/internal/utils.js
  function noop() {
  }
  var identity = (x) => x;
  function assign(tar, src) {
    for (const k in src) tar[k] = src[k];
    return (
      /** @type {T & S} */
      tar
    );
  }
  function run(fn) {
    return fn();
  }
  function blank_object() {
    return /* @__PURE__ */ Object.create(null);
  }
  function run_all(fns) {
    fns.forEach(run);
  }
  function is_function(thing) {
    return typeof thing === "function";
  }
  function safe_not_equal(a, b) {
    return a != a ? b == b : a !== b || a && typeof a === "object" || typeof a === "function";
  }
  function is_empty(obj) {
    return Object.keys(obj).length === 0;
  }
  function subscribe(store, ...callbacks) {
    if (store == null) {
      for (const callback of callbacks) {
        callback(void 0);
      }
      return noop;
    }
    const unsub = store.subscribe(...callbacks);
    return unsub.unsubscribe ? () => unsub.unsubscribe() : unsub;
  }
  function component_subscribe(component, store, callback) {
    component.$$.on_destroy.push(subscribe(store, callback));
  }

  // node_modules/svelte/src/runtime/internal/environment.js
  var is_client = typeof window !== "undefined";
  var now = is_client ? () => window.performance.now() : () => Date.now();
  var raf = is_client ? (cb) => requestAnimationFrame(cb) : noop;

  // node_modules/svelte/src/runtime/internal/loop.js
  var tasks = /* @__PURE__ */ new Set();
  function run_tasks(now2) {
    tasks.forEach((task) => {
      if (!task.c(now2)) {
        tasks.delete(task);
        task.f();
      }
    });
    if (tasks.size !== 0) raf(run_tasks);
  }
  function loop(callback) {
    let task;
    if (tasks.size === 0) raf(run_tasks);
    return {
      promise: new Promise((fulfill) => {
        tasks.add(task = { c: callback, f: fulfill });
      }),
      abort() {
        tasks.delete(task);
      }
    };
  }

  // node_modules/svelte/src/runtime/internal/globals.js
  var globals = typeof window !== "undefined" ? window : typeof globalThis !== "undefined" ? globalThis : (
    // @ts-ignore Node typings have this
    global
  );

  // node_modules/svelte/src/runtime/internal/ResizeObserverSingleton.js
  var ResizeObserverSingleton = class _ResizeObserverSingleton {
    /** @param {ResizeObserverOptions} options */
    constructor(options) {
      /**
       * @private
       * @readonly
       * @type {WeakMap<Element, import('./private.js').Listener>}
       */
      __publicField(this, "_listeners", "WeakMap" in globals ? /* @__PURE__ */ new WeakMap() : void 0);
      /**
       * @private
       * @type {ResizeObserver}
       */
      __publicField(this, "_observer");
      /** @type {ResizeObserverOptions} */
      __publicField(this, "options");
      this.options = options;
    }
    /**
     * @param {Element} element
     * @param {import('./private.js').Listener} listener
     * @returns {() => void}
     */
    observe(element2, listener) {
      this._listeners.set(element2, listener);
      this._getObserver().observe(element2, this.options);
      return () => {
        this._listeners.delete(element2);
        this._observer.unobserve(element2);
      };
    }
    /**
     * @private
     */
    _getObserver() {
      var _a;
      return (_a = this._observer) != null ? _a : this._observer = new ResizeObserver((entries) => {
        var _a2;
        for (const entry of entries) {
          _ResizeObserverSingleton.entries.set(entry.target, entry);
          (_a2 = this._listeners.get(entry.target)) == null ? void 0 : _a2(entry);
        }
      });
    }
  };
  ResizeObserverSingleton.entries = "WeakMap" in globals ? /* @__PURE__ */ new WeakMap() : void 0;

  // node_modules/svelte/src/runtime/internal/dom.js
  var is_hydrating = false;
  function start_hydrating() {
    is_hydrating = true;
  }
  function end_hydrating() {
    is_hydrating = false;
  }
  function append(target, node) {
    target.appendChild(node);
  }
  function get_root_for_style(node) {
    if (!node) return document;
    const root = node.getRootNode ? node.getRootNode() : node.ownerDocument;
    if (root && /** @type {ShadowRoot} */
    root.host) {
      return (
        /** @type {ShadowRoot} */
        root
      );
    }
    return node.ownerDocument;
  }
  function append_empty_stylesheet(node) {
    const style_element = element("style");
    style_element.textContent = "/* empty */";
    append_stylesheet(get_root_for_style(node), style_element);
    return style_element.sheet;
  }
  function append_stylesheet(node, style) {
    append(
      /** @type {Document} */
      node.head || node,
      style
    );
    return style.sheet;
  }
  function insert(target, node, anchor) {
    target.insertBefore(node, anchor || null);
  }
  function detach(node) {
    if (node.parentNode) {
      node.parentNode.removeChild(node);
    }
  }
  function element(name) {
    return document.createElement(name);
  }
  function text(data) {
    return document.createTextNode(data);
  }
  function space() {
    return text(" ");
  }
  function listen(node, event, handler, options) {
    node.addEventListener(event, handler, options);
    return () => node.removeEventListener(event, handler, options);
  }
  function attr(node, attribute, value) {
    if (value == null) node.removeAttribute(attribute);
    else if (node.getAttribute(attribute) !== value) node.setAttribute(attribute, value);
  }
  function children(element2) {
    return Array.from(element2.childNodes);
  }
  function set_data(text2, data) {
    data = "" + data;
    if (text2.data === data) return;
    text2.data = /** @type {string} */
    data;
  }
  function set_input_value(input, value) {
    input.value = value == null ? "" : value;
  }
  function set_style(node, key, value, important) {
    if (value == null) {
      node.style.removeProperty(key);
    } else {
      node.style.setProperty(key, value, important ? "important" : "");
    }
  }
  function select_option(select, value, mounting) {
    for (let i = 0; i < select.options.length; i += 1) {
      const option = select.options[i];
      if (option.__value === value) {
        option.selected = true;
        return;
      }
    }
    if (!mounting || value !== void 0) {
      select.selectedIndex = -1;
    }
  }
  function select_value(select) {
    const selected_option = select.querySelector(":checked");
    return selected_option && selected_option.__value;
  }
  function toggle_class(element2, name, toggle) {
    element2.classList.toggle(name, !!toggle);
  }
  function custom_event(type, detail, { bubbles = false, cancelable = false } = {}) {
    return new CustomEvent(type, { detail, bubbles, cancelable });
  }
  function get_custom_elements_slots(element2) {
    const result = {};
    element2.childNodes.forEach(
      /** @param {Element} node */
      (node) => {
        result[node.slot || "default"] = true;
      }
    );
    return result;
  }

  // node_modules/svelte/src/runtime/internal/style_manager.js
  var managed_styles = /* @__PURE__ */ new Map();
  var active = 0;
  function hash(str) {
    let hash2 = 5381;
    let i = str.length;
    while (i--) hash2 = (hash2 << 5) - hash2 ^ str.charCodeAt(i);
    return hash2 >>> 0;
  }
  function create_style_information(doc, node) {
    const info = { stylesheet: append_empty_stylesheet(node), rules: {} };
    managed_styles.set(doc, info);
    return info;
  }
  function create_rule(node, a, b, duration, delay, ease, fn, uid = 0) {
    const step = 16.666 / duration;
    let keyframes = "{\n";
    for (let p = 0; p <= 1; p += step) {
      const t = a + (b - a) * ease(p);
      keyframes += p * 100 + `%{${fn(t, 1 - t)}}
`;
    }
    const rule = keyframes + `100% {${fn(b, 1 - b)}}
}`;
    const name = `__svelte_${hash(rule)}_${uid}`;
    const doc = get_root_for_style(node);
    const { stylesheet, rules } = managed_styles.get(doc) || create_style_information(doc, node);
    if (!rules[name]) {
      rules[name] = true;
      stylesheet.insertRule(`@keyframes ${name} ${rule}`, stylesheet.cssRules.length);
    }
    const animation = node.style.animation || "";
    node.style.animation = `${animation ? `${animation}, ` : ""}${name} ${duration}ms linear ${delay}ms 1 both`;
    active += 1;
    return name;
  }
  function delete_rule(node, name) {
    const previous = (node.style.animation || "").split(", ");
    const next = previous.filter(
      name ? (anim) => anim.indexOf(name) < 0 : (anim) => anim.indexOf("__svelte") === -1
      // remove all Svelte animations
    );
    const deleted = previous.length - next.length;
    if (deleted) {
      node.style.animation = next.join(", ");
      active -= deleted;
      if (!active) clear_rules();
    }
  }
  function clear_rules() {
    raf(() => {
      if (active) return;
      managed_styles.forEach((info) => {
        const { ownerNode } = info.stylesheet;
        if (ownerNode) detach(ownerNode);
      });
      managed_styles.clear();
    });
  }

  // node_modules/svelte/src/runtime/internal/lifecycle.js
  var current_component;
  function set_current_component(component) {
    current_component = component;
  }

  // node_modules/svelte/src/runtime/internal/scheduler.js
  var dirty_components = [];
  var binding_callbacks = [];
  var render_callbacks = [];
  var flush_callbacks = [];
  var resolved_promise = /* @__PURE__ */ Promise.resolve();
  var update_scheduled = false;
  function schedule_update() {
    if (!update_scheduled) {
      update_scheduled = true;
      resolved_promise.then(flush);
    }
  }
  function add_render_callback(fn) {
    render_callbacks.push(fn);
  }
  var seen_callbacks = /* @__PURE__ */ new Set();
  var flushidx = 0;
  function flush() {
    if (flushidx !== 0) {
      return;
    }
    const saved_component = current_component;
    do {
      try {
        while (flushidx < dirty_components.length) {
          const component = dirty_components[flushidx];
          flushidx++;
          set_current_component(component);
          update(component.$$);
        }
      } catch (e) {
        dirty_components.length = 0;
        flushidx = 0;
        throw e;
      }
      set_current_component(null);
      dirty_components.length = 0;
      flushidx = 0;
      while (binding_callbacks.length) binding_callbacks.pop()();
      for (let i = 0; i < render_callbacks.length; i += 1) {
        const callback = render_callbacks[i];
        if (!seen_callbacks.has(callback)) {
          seen_callbacks.add(callback);
          callback();
        }
      }
      render_callbacks.length = 0;
    } while (dirty_components.length);
    while (flush_callbacks.length) {
      flush_callbacks.pop()();
    }
    update_scheduled = false;
    seen_callbacks.clear();
    set_current_component(saved_component);
  }
  function update($$) {
    if ($$.fragment !== null) {
      $$.update();
      run_all($$.before_update);
      const dirty = $$.dirty;
      $$.dirty = [-1];
      $$.fragment && $$.fragment.p($$.ctx, dirty);
      $$.after_update.forEach(add_render_callback);
    }
  }
  function flush_render_callbacks(fns) {
    const filtered = [];
    const targets = [];
    render_callbacks.forEach((c) => fns.indexOf(c) === -1 ? filtered.push(c) : targets.push(c));
    targets.forEach((c) => c());
    render_callbacks = filtered;
  }

  // node_modules/svelte/src/runtime/internal/transitions.js
  var promise;
  function wait() {
    if (!promise) {
      promise = Promise.resolve();
      promise.then(() => {
        promise = null;
      });
    }
    return promise;
  }
  function dispatch(node, direction, kind) {
    node.dispatchEvent(custom_event(`${direction ? "intro" : "outro"}${kind}`));
  }
  var outroing = /* @__PURE__ */ new Set();
  var outros;
  function group_outros() {
    outros = {
      r: 0,
      c: [],
      p: outros
      // parent group
    };
  }
  function check_outros() {
    if (!outros.r) {
      run_all(outros.c);
    }
    outros = outros.p;
  }
  function transition_in(block, local) {
    if (block && block.i) {
      outroing.delete(block);
      block.i(local);
    }
  }
  function transition_out(block, local, detach2, callback) {
    if (block && block.o) {
      if (outroing.has(block)) return;
      outroing.add(block);
      outros.c.push(() => {
        outroing.delete(block);
        if (callback) {
          if (detach2) block.d(1);
          callback();
        }
      });
      block.o(local);
    } else if (callback) {
      callback();
    }
  }
  var null_transition = { duration: 0 };
  function create_bidirectional_transition(node, fn, params, intro) {
    const options = { direction: "both" };
    let config = fn(node, params, options);
    let t = intro ? 0 : 1;
    let running_program = null;
    let pending_program = null;
    let animation_name = null;
    let original_inert_value;
    function clear_animation() {
      if (animation_name) delete_rule(node, animation_name);
    }
    function init2(program, duration) {
      const d = (
        /** @type {Program['d']} */
        program.b - t
      );
      duration *= Math.abs(d);
      return {
        a: t,
        b: program.b,
        d,
        duration,
        start: program.start,
        end: program.start + duration,
        group: program.group
      };
    }
    function go(b) {
      const {
        delay = 0,
        duration = 300,
        easing = identity,
        tick = noop,
        css
      } = config || null_transition;
      const program = {
        start: now() + delay,
        b
      };
      if (!b) {
        program.group = outros;
        outros.r += 1;
      }
      if ("inert" in node) {
        if (b) {
          if (original_inert_value !== void 0) {
            node.inert = original_inert_value;
          }
        } else {
          original_inert_value = /** @type {HTMLElement} */
          node.inert;
          node.inert = true;
        }
      }
      if (running_program || pending_program) {
        pending_program = program;
      } else {
        if (css) {
          clear_animation();
          animation_name = create_rule(node, t, b, duration, delay, easing, css);
        }
        if (b) tick(0, 1);
        running_program = init2(program, duration);
        add_render_callback(() => dispatch(node, b, "start"));
        loop((now2) => {
          if (pending_program && now2 > pending_program.start) {
            running_program = init2(pending_program, duration);
            pending_program = null;
            dispatch(node, running_program.b, "start");
            if (css) {
              clear_animation();
              animation_name = create_rule(
                node,
                t,
                running_program.b,
                running_program.duration,
                0,
                easing,
                config.css
              );
            }
          }
          if (running_program) {
            if (now2 >= running_program.end) {
              tick(t = running_program.b, 1 - t);
              dispatch(node, running_program.b, "end");
              if (!pending_program) {
                if (running_program.b) {
                  clear_animation();
                } else {
                  if (!--running_program.group.r) run_all(running_program.group.c);
                }
              }
              running_program = null;
            } else if (now2 >= running_program.start) {
              const p = now2 - running_program.start;
              t = running_program.a + running_program.d * easing(p / running_program.duration);
              tick(t, 1 - t);
            }
          }
          return !!(running_program || pending_program);
        });
      }
    }
    return {
      run(b) {
        if (is_function(config)) {
          wait().then(() => {
            const opts = { direction: b ? "in" : "out" };
            config = config(opts);
            go(b);
          });
        } else {
          go(b);
        }
      },
      end() {
        clear_animation();
        running_program = pending_program = null;
      }
    };
  }

  // node_modules/svelte/src/runtime/internal/each.js
  function ensure_array_like(array_like_or_iterator) {
    return (array_like_or_iterator == null ? void 0 : array_like_or_iterator.length) !== void 0 ? array_like_or_iterator : Array.from(array_like_or_iterator);
  }
  function destroy_block(block, lookup) {
    block.d(1);
    lookup.delete(block.key);
  }
  function update_keyed_each(old_blocks, dirty, get_key, dynamic, ctx, list, lookup, node, destroy, create_each_block2, next, get_context) {
    let o = old_blocks.length;
    let n = list.length;
    let i = o;
    const old_indexes = {};
    while (i--) old_indexes[old_blocks[i].key] = i;
    const new_blocks = [];
    const new_lookup = /* @__PURE__ */ new Map();
    const deltas = /* @__PURE__ */ new Map();
    const updates = [];
    i = n;
    while (i--) {
      const child_ctx = get_context(ctx, list, i);
      const key = get_key(child_ctx);
      let block = lookup.get(key);
      if (!block) {
        block = create_each_block2(key, child_ctx);
        block.c();
      } else if (dynamic) {
        updates.push(() => block.p(child_ctx, dirty));
      }
      new_lookup.set(key, new_blocks[i] = block);
      if (key in old_indexes) deltas.set(key, Math.abs(i - old_indexes[key]));
    }
    const will_move = /* @__PURE__ */ new Set();
    const did_move = /* @__PURE__ */ new Set();
    function insert2(block) {
      transition_in(block, 1);
      block.m(node, next);
      lookup.set(block.key, block);
      next = block.first;
      n--;
    }
    while (o && n) {
      const new_block = new_blocks[n - 1];
      const old_block = old_blocks[o - 1];
      const new_key = new_block.key;
      const old_key = old_block.key;
      if (new_block === old_block) {
        next = new_block.first;
        o--;
        n--;
      } else if (!new_lookup.has(old_key)) {
        destroy(old_block, lookup);
        o--;
      } else if (!lookup.has(new_key) || will_move.has(new_key)) {
        insert2(new_block);
      } else if (did_move.has(old_key)) {
        o--;
      } else if (deltas.get(new_key) > deltas.get(old_key)) {
        did_move.add(new_key);
        insert2(new_block);
      } else {
        will_move.add(old_key);
        o--;
      }
    }
    while (o--) {
      const old_block = old_blocks[o];
      if (!new_lookup.has(old_block.key)) destroy(old_block, lookup);
    }
    while (n) insert2(new_blocks[n - 1]);
    run_all(updates);
    return new_blocks;
  }

  // node_modules/svelte/src/shared/boolean_attributes.js
  var _boolean_attributes = (
    /** @type {const} */
    [
      "allowfullscreen",
      "allowpaymentrequest",
      "async",
      "autofocus",
      "autoplay",
      "checked",
      "controls",
      "default",
      "defer",
      "disabled",
      "formnovalidate",
      "hidden",
      "inert",
      "ismap",
      "loop",
      "multiple",
      "muted",
      "nomodule",
      "novalidate",
      "open",
      "playsinline",
      "readonly",
      "required",
      "reversed",
      "selected"
    ]
  );
  var boolean_attributes = /* @__PURE__ */ new Set([..._boolean_attributes]);

  // node_modules/svelte/src/runtime/internal/Component.js
  function mount_component(component, target, anchor) {
    const { fragment, after_update } = component.$$;
    fragment && fragment.m(target, anchor);
    add_render_callback(() => {
      const new_on_destroy = component.$$.on_mount.map(run).filter(is_function);
      if (component.$$.on_destroy) {
        component.$$.on_destroy.push(...new_on_destroy);
      } else {
        run_all(new_on_destroy);
      }
      component.$$.on_mount = [];
    });
    after_update.forEach(add_render_callback);
  }
  function destroy_component(component, detaching) {
    const $$ = component.$$;
    if ($$.fragment !== null) {
      flush_render_callbacks($$.after_update);
      run_all($$.on_destroy);
      $$.fragment && $$.fragment.d(detaching);
      $$.on_destroy = $$.fragment = null;
      $$.ctx = [];
    }
  }
  function make_dirty(component, i) {
    if (component.$$.dirty[0] === -1) {
      dirty_components.push(component);
      schedule_update();
      component.$$.dirty.fill(0);
    }
    component.$$.dirty[i / 31 | 0] |= 1 << i % 31;
  }
  function init(component, options, instance2, create_fragment2, not_equal, props, append_styles = null, dirty = [-1]) {
    const parent_component = current_component;
    set_current_component(component);
    const $$ = component.$$ = {
      fragment: null,
      ctx: [],
      // state
      props,
      update: noop,
      not_equal,
      bound: blank_object(),
      // lifecycle
      on_mount: [],
      on_destroy: [],
      on_disconnect: [],
      before_update: [],
      after_update: [],
      context: new Map(options.context || (parent_component ? parent_component.$$.context : [])),
      // everything else
      callbacks: blank_object(),
      dirty,
      skip_bound: false,
      root: options.target || parent_component.$$.root
    };
    append_styles && append_styles($$.root);
    let ready = false;
    $$.ctx = instance2 ? instance2(component, options.props || {}, (i, ret, ...rest) => {
      const value = rest.length ? rest[0] : ret;
      if ($$.ctx && not_equal($$.ctx[i], $$.ctx[i] = value)) {
        if (!$$.skip_bound && $$.bound[i]) $$.bound[i](value);
        if (ready) make_dirty(component, i);
      }
      return ret;
    }) : [];
    $$.update();
    ready = true;
    run_all($$.before_update);
    $$.fragment = create_fragment2 ? create_fragment2($$.ctx) : false;
    if (options.target) {
      if (options.hydrate) {
        start_hydrating();
        const nodes = children(options.target);
        $$.fragment && $$.fragment.l(nodes);
        nodes.forEach(detach);
      } else {
        $$.fragment && $$.fragment.c();
      }
      if (options.intro) transition_in(component.$$.fragment);
      mount_component(component, options.target, options.anchor);
      end_hydrating();
      flush();
    }
    set_current_component(parent_component);
  }
  var SvelteElement;
  if (typeof HTMLElement === "function") {
    SvelteElement = class extends HTMLElement {
      constructor($$componentCtor, $$slots, use_shadow_dom) {
        super();
        /** The Svelte component constructor */
        __publicField(this, "$$ctor");
        /** Slots */
        __publicField(this, "$$s");
        /** The Svelte component instance */
        __publicField(this, "$$c");
        /** Whether or not the custom element is connected */
        __publicField(this, "$$cn", false);
        /** Component props data */
        __publicField(this, "$$d", {});
        /** `true` if currently in the process of reflecting component props back to attributes */
        __publicField(this, "$$r", false);
        /** @type {Record<string, CustomElementPropDefinition>} Props definition (name, reflected, type etc) */
        __publicField(this, "$$p_d", {});
        /** @type {Record<string, Function[]>} Event listeners */
        __publicField(this, "$$l", {});
        /** @type {Map<Function, Function>} Event listener unsubscribe functions */
        __publicField(this, "$$l_u", /* @__PURE__ */ new Map());
        this.$$ctor = $$componentCtor;
        this.$$s = $$slots;
        if (use_shadow_dom) {
          this.attachShadow({ mode: "open" });
        }
      }
      addEventListener(type, listener, options) {
        this.$$l[type] = this.$$l[type] || [];
        this.$$l[type].push(listener);
        if (this.$$c) {
          const unsub = this.$$c.$on(type, listener);
          this.$$l_u.set(listener, unsub);
        }
        super.addEventListener(type, listener, options);
      }
      removeEventListener(type, listener, options) {
        super.removeEventListener(type, listener, options);
        if (this.$$c) {
          const unsub = this.$$l_u.get(listener);
          if (unsub) {
            unsub();
            this.$$l_u.delete(listener);
          }
        }
        if (this.$$l[type]) {
          const idx = this.$$l[type].indexOf(listener);
          if (idx >= 0) {
            this.$$l[type].splice(idx, 1);
          }
        }
      }
      async connectedCallback() {
        this.$$cn = true;
        if (!this.$$c) {
          let create_slot = function(name) {
            return () => {
              let node;
              const obj = {
                c: function create() {
                  node = element("slot");
                  if (name !== "default") {
                    attr(node, "name", name);
                  }
                },
                /**
                 * @param {HTMLElement} target
                 * @param {HTMLElement} [anchor]
                 */
                m: function mount(target, anchor) {
                  insert(target, node, anchor);
                },
                d: function destroy(detaching) {
                  if (detaching) {
                    detach(node);
                  }
                }
              };
              return obj;
            };
          };
          await Promise.resolve();
          if (!this.$$cn || this.$$c) {
            return;
          }
          const $$slots = {};
          const existing_slots = get_custom_elements_slots(this);
          for (const name of this.$$s) {
            if (name in existing_slots) {
              $$slots[name] = [create_slot(name)];
            }
          }
          for (const attribute of this.attributes) {
            const name = this.$$g_p(attribute.name);
            if (!(name in this.$$d)) {
              this.$$d[name] = get_custom_element_value(name, attribute.value, this.$$p_d, "toProp");
            }
          }
          for (const key in this.$$p_d) {
            if (!(key in this.$$d) && this[key] !== void 0) {
              this.$$d[key] = this[key];
              delete this[key];
            }
          }
          this.$$c = new this.$$ctor({
            target: this.shadowRoot || this,
            props: {
              ...this.$$d,
              $$slots,
              $$scope: {
                ctx: []
              }
            }
          });
          const reflect_attributes = () => {
            this.$$r = true;
            for (const key in this.$$p_d) {
              this.$$d[key] = this.$$c.$$.ctx[this.$$c.$$.props[key]];
              if (this.$$p_d[key].reflect) {
                const attribute_value = get_custom_element_value(
                  key,
                  this.$$d[key],
                  this.$$p_d,
                  "toAttribute"
                );
                if (attribute_value == null) {
                  this.removeAttribute(this.$$p_d[key].attribute || key);
                } else {
                  this.setAttribute(this.$$p_d[key].attribute || key, attribute_value);
                }
              }
            }
            this.$$r = false;
          };
          this.$$c.$$.after_update.push(reflect_attributes);
          reflect_attributes();
          for (const type in this.$$l) {
            for (const listener of this.$$l[type]) {
              const unsub = this.$$c.$on(type, listener);
              this.$$l_u.set(listener, unsub);
            }
          }
          this.$$l = {};
        }
      }
      // We don't need this when working within Svelte code, but for compatibility of people using this outside of Svelte
      // and setting attributes through setAttribute etc, this is helpful
      attributeChangedCallback(attr2, _oldValue, newValue) {
        var _a;
        if (this.$$r) return;
        attr2 = this.$$g_p(attr2);
        this.$$d[attr2] = get_custom_element_value(attr2, newValue, this.$$p_d, "toProp");
        (_a = this.$$c) == null ? void 0 : _a.$set({ [attr2]: this.$$d[attr2] });
      }
      disconnectedCallback() {
        this.$$cn = false;
        Promise.resolve().then(() => {
          if (!this.$$cn && this.$$c) {
            this.$$c.$destroy();
            this.$$c = void 0;
          }
        });
      }
      $$g_p(attribute_name) {
        return Object.keys(this.$$p_d).find(
          (key) => this.$$p_d[key].attribute === attribute_name || !this.$$p_d[key].attribute && key.toLowerCase() === attribute_name
        ) || attribute_name;
      }
    };
  }
  function get_custom_element_value(prop, value, props_definition, transform) {
    var _a;
    const type = (_a = props_definition[prop]) == null ? void 0 : _a.type;
    value = type === "Boolean" && typeof value !== "boolean" ? value != null : value;
    if (!transform || !props_definition[prop]) {
      return value;
    } else if (transform === "toAttribute") {
      switch (type) {
        case "Object":
        case "Array":
          return value == null ? null : JSON.stringify(value);
        case "Boolean":
          return value ? "" : null;
        case "Number":
          return value == null ? null : value;
        default:
          return value;
      }
    } else {
      switch (type) {
        case "Object":
        case "Array":
          return value && JSON.parse(value);
        case "Boolean":
          return value;
        // conversion already handled above
        case "Number":
          return value != null ? +value : value;
        default:
          return value;
      }
    }
  }
  var SvelteComponent = class {
    constructor() {
      /**
       * ### PRIVATE API
       *
       * Do not use, may change at any time
       *
       * @type {any}
       */
      __publicField(this, "$$");
      /**
       * ### PRIVATE API
       *
       * Do not use, may change at any time
       *
       * @type {any}
       */
      __publicField(this, "$$set");
    }
    /** @returns {void} */
    $destroy() {
      destroy_component(this, 1);
      this.$destroy = noop;
    }
    /**
     * @template {Extract<keyof Events, string>} K
     * @param {K} type
     * @param {((e: Events[K]) => void) | null | undefined} callback
     * @returns {() => void}
     */
    $on(type, callback) {
      if (!is_function(callback)) {
        return noop;
      }
      const callbacks = this.$$.callbacks[type] || (this.$$.callbacks[type] = []);
      callbacks.push(callback);
      return () => {
        const index = callbacks.indexOf(callback);
        if (index !== -1) callbacks.splice(index, 1);
      };
    }
    /**
     * @param {Partial<Props>} props
     * @returns {void}
     */
    $set(props) {
      if (this.$$set && !is_empty(props)) {
        this.$$.skip_bound = true;
        this.$$set(props);
        this.$$.skip_bound = false;
      }
    }
  };

  // node_modules/svelte/src/shared/version.js
  var PUBLIC_VERSION = "4";

  // node_modules/svelte/src/runtime/internal/disclose-version/index.js
  if (typeof window !== "undefined")
    (window.__svelte || (window.__svelte = { v: /* @__PURE__ */ new Set() })).v.add(PUBLIC_VERSION);

  // node_modules/svelte/src/runtime/store/index.js
  var subscriber_queue = [];
  function readable(value, start) {
    return {
      subscribe: writable(value, start).subscribe
    };
  }
  function writable(value, start = noop) {
    let stop;
    const subscribers = /* @__PURE__ */ new Set();
    function set(new_value) {
      if (safe_not_equal(value, new_value)) {
        value = new_value;
        if (stop) {
          const run_queue = !subscriber_queue.length;
          for (const subscriber of subscribers) {
            subscriber[1]();
            subscriber_queue.push(subscriber, value);
          }
          if (run_queue) {
            for (let i = 0; i < subscriber_queue.length; i += 2) {
              subscriber_queue[i][0](subscriber_queue[i + 1]);
            }
            subscriber_queue.length = 0;
          }
        }
      }
    }
    function update2(fn) {
      set(fn(value));
    }
    function subscribe2(run2, invalidate = noop) {
      const subscriber = [run2, invalidate];
      subscribers.add(subscriber);
      if (subscribers.size === 1) {
        stop = start(set, update2) || noop;
      }
      run2(value);
      return () => {
        subscribers.delete(subscriber);
        if (subscribers.size === 0 && stop) {
          stop();
          stop = null;
        }
      };
    }
    return { set, update: update2, subscribe: subscribe2 };
  }
  function derived(stores, fn, initial_value) {
    const single = !Array.isArray(stores);
    const stores_array = single ? [stores] : stores;
    if (!stores_array.every(Boolean)) {
      throw new Error("derived() expects stores as input, got a falsy value");
    }
    const auto = fn.length < 2;
    return readable(initial_value, (set, update2) => {
      let started = false;
      const values = [];
      let pending = 0;
      let cleanup = noop;
      const sync = () => {
        if (pending) {
          return;
        }
        cleanup();
        const result = fn(single ? values[0] : values, set, update2);
        if (auto) {
          set(result);
        } else {
          cleanup = is_function(result) ? result : noop;
        }
      };
      const unsubscribers = stores_array.map(
        (store, i) => subscribe(
          store,
          (value) => {
            values[i] = value;
            pending &= ~(1 << i);
            if (started) {
              sync();
            }
          },
          () => {
            pending |= 1 << i;
          }
        )
      );
      started = true;
      sync();
      return function stop() {
        run_all(unsubscribers);
        cleanup();
        started = false;
      };
    });
  }

  // node_modules/svelte/src/runtime/motion/utils.js
  function is_date(obj) {
    return Object.prototype.toString.call(obj) === "[object Date]";
  }

  // node_modules/svelte/src/runtime/easing/index.js
  function cubicOut(t) {
    const f = t - 1;
    return f * f * f + 1;
  }

  // node_modules/svelte/src/runtime/motion/tweened.js
  function get_interpolator(a, b) {
    if (a === b || a !== a) return () => a;
    const type = typeof a;
    if (type !== typeof b || Array.isArray(a) !== Array.isArray(b)) {
      throw new Error("Cannot interpolate values of different type");
    }
    if (Array.isArray(a)) {
      const arr = b.map((bi, i) => {
        return get_interpolator(a[i], bi);
      });
      return (t) => arr.map((fn) => fn(t));
    }
    if (type === "object") {
      if (!a || !b) throw new Error("Object cannot be null");
      if (is_date(a) && is_date(b)) {
        a = a.getTime();
        b = b.getTime();
        const delta = b - a;
        return (t) => new Date(a + t * delta);
      }
      const keys = Object.keys(b);
      const interpolators = {};
      keys.forEach((key) => {
        interpolators[key] = get_interpolator(a[key], b[key]);
      });
      return (t) => {
        const result = {};
        keys.forEach((key) => {
          result[key] = interpolators[key](t);
        });
        return result;
      };
    }
    if (type === "number") {
      const delta = b - a;
      return (t) => a + t * delta;
    }
    throw new Error(`Cannot interpolate ${type} values`);
  }
  function tweened(value, defaults = {}) {
    const store = writable(value);
    let task;
    let target_value = value;
    function set(new_value, opts) {
      if (value == null) {
        store.set(value = new_value);
        return Promise.resolve();
      }
      target_value = new_value;
      let previous_task = task;
      let started = false;
      let {
        delay = 0,
        duration = 400,
        easing = identity,
        interpolate = get_interpolator
      } = assign(assign({}, defaults), opts);
      if (duration === 0) {
        if (previous_task) {
          previous_task.abort();
          previous_task = null;
        }
        store.set(value = target_value);
        return Promise.resolve();
      }
      const start = now() + delay;
      let fn;
      task = loop((now2) => {
        if (now2 < start) return true;
        if (!started) {
          fn = interpolate(value, new_value);
          if (typeof duration === "function") duration = duration(value, new_value);
          started = true;
        }
        if (previous_task) {
          previous_task.abort();
          previous_task = null;
        }
        const elapsed = now2 - start;
        if (elapsed > /** @type {number} */
        duration) {
          store.set(value = new_value);
          return false;
        }
        store.set(value = fn(easing(elapsed / duration)));
        return true;
      });
      return task.promise;
    }
    return {
      set,
      update: (fn, opts) => set(fn(target_value, value), opts),
      subscribe: store.subscribe
    };
  }

  // node_modules/svelte/src/runtime/transition/index.js
  function fade(node, { delay = 0, duration = 400, easing = identity } = {}) {
    const o = +getComputedStyle(node).opacity;
    return {
      delay,
      duration,
      easing,
      css: (t) => `opacity: ${t * o}`
    };
  }

  // src/Showcase.svelte
  function get_each_context(ctx, list, i) {
    const child_ctx = ctx.slice();
    child_ctx[29] = list[i];
    child_ctx[31] = i;
    return child_ctx;
  }
  function create_else_block_2(ctx) {
    let div;
    let t;
    return {
      c() {
        div = element("div");
        t = text("The cart is empty.");
        attr(div, "class", "fw-note");
        set_style(div, "left", "16px");
        set_style(div, "top", ROW_TOP + "px");
        set_style(div, "width", "448px");
        set_style(div, "height", "20px");
      },
      m(target, anchor) {
        insert(target, div, anchor);
        append(div, t);
      },
      p: noop,
      d(detaching) {
        if (detaching) {
          detach(div);
        }
      }
    };
  }
  function create_each_block(key_1, ctx) {
    let div5;
    let div0;
    let t0;
    let div1;
    let t1_value = (
      /*it*/
      ctx[29].name + ""
    );
    let t1;
    let t2;
    let t3_value = (
      /*it*/
      ctx[29].price + ""
    );
    let t3;
    let t4;
    let button0;
    let t6;
    let div2;
    let t7_value = (
      /*it*/
      ctx[29].qty + ""
    );
    let t7;
    let t8;
    let button1;
    let t10;
    let div4;
    let div3;
    let t11;
    let button2;
    let mounted;
    let dispose;
    function click_handler() {
      return (
        /*click_handler*/
        ctx[20](
          /*it*/
          ctx[29]
        )
      );
    }
    function click_handler_1() {
      return (
        /*click_handler_1*/
        ctx[21](
          /*it*/
          ctx[29]
        )
      );
    }
    function click_handler_2() {
      return (
        /*click_handler_2*/
        ctx[22](
          /*it*/
          ctx[29]
        )
      );
    }
    return {
      key: key_1,
      first: null,
      c() {
        div5 = element("div");
        div0 = element("div");
        t0 = space();
        div1 = element("div");
        t1 = text(t1_value);
        t2 = text(" $");
        t3 = text(t3_value);
        t4 = space();
        button0 = element("button");
        button0.textContent = "-";
        t6 = space();
        div2 = element("div");
        t7 = text(t7_value);
        t8 = space();
        button1 = element("button");
        button1.textContent = "+";
        t10 = space();
        div4 = element("div");
        div3 = element("div");
        t11 = space();
        button2 = element("button");
        button2.textContent = "x";
        attr(div0, "class", "fw-swatch");
        set_style(div0, "left", "6px");
        set_style(div0, "top", "5px");
        set_style(div0, "width", "14px");
        set_style(div0, "height", "14px");
        set_style(
          div0,
          "background",
          /*it*/
          ctx[29].color
        );
        attr(div1, "class", "fw-row-text");
        set_style(div1, "left", "28px");
        set_style(div1, "top", "2px");
        set_style(div1, "width", "150px");
        set_style(div1, "height", "20px");
        attr(button0, "class", "fw-btn");
        set_style(button0, "left", "186px");
        set_style(button0, "top", "2px");
        set_style(button0, "width", "24px");
        set_style(button0, "height", "20px");
        attr(div2, "class", "fw-row-text");
        set_style(div2, "left", "216px");
        set_style(div2, "top", "2px");
        set_style(div2, "width", "20px");
        set_style(div2, "height", "20px");
        attr(button1, "class", "fw-btn");
        set_style(button1, "left", "238px");
        set_style(button1, "top", "2px");
        set_style(button1, "width", "24px");
        set_style(button1, "height", "20px");
        attr(div3, "class", "fw-fill");
        set_style(div3, "left", "0px");
        set_style(div3, "top", "0px");
        set_style(div3, "width", BAR_UNIT * /*it*/
        ctx[29].qty + "px");
        set_style(div3, "height", "10px");
        attr(div4, "class", "fw-track");
        set_style(div4, "left", "272px");
        set_style(div4, "top", "8px");
        set_style(div4, "width", BAR_UNIT * MAX_QTY + "px");
        set_style(div4, "height", "10px");
        attr(button2, "class", "fw-btn fw-remove");
        set_style(button2, "left", "410px");
        set_style(button2, "top", "2px");
        set_style(button2, "width", "32px");
        set_style(button2, "height", "20px");
        attr(div5, "class", "fw-row");
        set_style(div5, "left", "16px");
        set_style(div5, "top", ROW_TOP + /*i*/
        ctx[31] * ROW_STEP + "px");
        set_style(div5, "width", "448px");
        set_style(div5, "height", "26px");
        this.first = div5;
      },
      m(target, anchor) {
        insert(target, div5, anchor);
        append(div5, div0);
        append(div5, t0);
        append(div5, div1);
        append(div1, t1);
        append(div1, t2);
        append(div1, t3);
        append(div5, t4);
        append(div5, button0);
        append(div5, t6);
        append(div5, div2);
        append(div2, t7);
        append(div5, t8);
        append(div5, button1);
        append(div5, t10);
        append(div5, div4);
        append(div4, div3);
        append(div5, t11);
        append(div5, button2);
        if (!mounted) {
          dispose = [
            listen(button0, "click", click_handler),
            listen(button1, "click", click_handler_1),
            listen(button2, "click", click_handler_2)
          ];
          mounted = true;
        }
      },
      p(new_ctx, dirty) {
        ctx = new_ctx;
        if (dirty[0] & /*$cart*/
        64) {
          set_style(
            div0,
            "background",
            /*it*/
            ctx[29].color
          );
        }
        if (dirty[0] & /*$cart*/
        64 && t1_value !== (t1_value = /*it*/
        ctx[29].name + "")) set_data(t1, t1_value);
        if (dirty[0] & /*$cart*/
        64 && t3_value !== (t3_value = /*it*/
        ctx[29].price + "")) set_data(t3, t3_value);
        if (dirty[0] & /*$cart*/
        64 && t7_value !== (t7_value = /*it*/
        ctx[29].qty + "")) set_data(t7, t7_value);
        if (dirty[0] & /*$cart*/
        64) {
          set_style(div3, "width", BAR_UNIT * /*it*/
          ctx[29].qty + "px");
        }
        if (dirty[0] & /*$cart*/
        64) {
          set_style(div5, "top", ROW_TOP + /*i*/
          ctx[31] * ROW_STEP + "px");
        }
      },
      d(detaching) {
        if (detaching) {
          detach(div5);
        }
        mounted = false;
        run_all(dispose);
      }
    };
  }
  function create_else_block_1(ctx) {
    let div;
    return {
      c() {
        div = element("div");
        div.textContent = "format ABCD12";
        attr(div, "class", "fw-note");
        set_style(div, "left", "730px");
        set_style(div, "top", "76px");
        set_style(div, "width", "210px");
        set_style(div, "height", "20px");
      },
      m(target, anchor) {
        insert(target, div, anchor);
      },
      p: noop,
      i: noop,
      o: noop,
      d(detaching) {
        if (detaching) {
          detach(div);
        }
      }
    };
  }
  function create_if_block_1(ctx) {
    let div;
    let t0;
    let t1;
    let div_transition;
    let current;
    return {
      c() {
        div = element("div");
        t0 = text("applied: -$");
        t1 = text(
          /*discount*/
          ctx[3]
        );
        attr(div, "class", "fw-note ok");
        set_style(div, "left", "730px");
        set_style(div, "top", "76px");
        set_style(div, "width", "210px");
        set_style(div, "height", "20px");
      },
      m(target, anchor) {
        insert(target, div, anchor);
        append(div, t0);
        append(div, t1);
        current = true;
      },
      p(ctx2, dirty) {
        if (!current || dirty[0] & /*discount*/
        8) set_data(
          t1,
          /*discount*/
          ctx2[3]
        );
      },
      i(local) {
        if (current) return;
        if (local) {
          add_render_callback(() => {
            if (!current) return;
            if (!div_transition) div_transition = create_bidirectional_transition(div, fade, { duration: 200 }, true);
            div_transition.run(1);
          });
        }
        current = true;
      },
      o(local) {
        if (local) {
          if (!div_transition) div_transition = create_bidirectional_transition(div, fade, { duration: 200 }, false);
          div_transition.run(0);
        }
        current = false;
      },
      d(detaching) {
        if (detaching) {
          detach(div);
        }
        if (detaching && div_transition) div_transition.end();
      }
    };
  }
  function create_else_block(ctx) {
    let t;
    return {
      c() {
        t = text("Gift wrap");
      },
      m(target, anchor) {
        insert(target, t, anchor);
      },
      d(detaching) {
        if (detaching) {
          detach(t);
        }
      }
    };
  }
  function create_if_block(ctx) {
    let t;
    return {
      c() {
        t = text("Gift wrap added (+$3)");
      },
      m(target, anchor) {
        insert(target, t, anchor);
      },
      d(detaching) {
        if (detaching) {
          detach(t);
        }
      }
    };
  }
  function create_fragment(ctx) {
    let div13;
    let div0;
    let t1;
    let button0;
    let t2;
    let button0_disabled_value;
    let t3;
    let div1;
    let t4;
    let t5;
    let t6_value = (
      /*$itemCount*/
      ctx[9] === 1 ? "" : "s"
    );
    let t6;
    let t7;
    let t8;
    let t9;
    let each_blocks = [];
    let each_1_lookup = /* @__PURE__ */ new Map();
    let t10;
    let div2;
    let t12;
    let div3;
    let t14;
    let input0;
    let t15;
    let div4;
    let t16;
    let current_block_type_index;
    let if_block0;
    let t17;
    let div5;
    let t19;
    let select;
    let option0;
    let option1;
    let option2;
    let t23;
    let div6;
    let t24;
    let t25;
    let t26;
    let t27_value = (
      /*SHIPPING*/
      ctx[16][
        /*shipping*/
        ctx[1]
      ] + ""
    );
    let t27;
    let t28;
    let t29;
    let input1;
    let t30;
    let div7;
    let t31;
    let div8;
    let t33;
    let div9;
    let t34;
    let t35;
    let t36;
    let button1;
    let t37;
    let button1_disabled_value;
    let t38;
    let button2;
    let t40;
    let div11;
    let div10;
    let t41;
    let div12;
    let t42_value = (
      /*checkedOut*/
      ctx[7] ? (
        /*$progress*/
        ctx[10] >= 1 ? "Order placed." : "Placing order... " + Math.round(
          /*$progress*/
          ctx[10] * 100
        ) + "%"
      ) : "Not checked out"
    );
    let t42;
    let mounted;
    let dispose;
    let each_value = ensure_array_like(
      /*$cart*/
      ctx[6]
    );
    const get_key = (ctx2) => (
      /*it*/
      ctx2[29].id
    );
    for (let i = 0; i < each_value.length; i += 1) {
      let child_ctx = get_each_context(ctx, each_value, i);
      let key = get_key(child_ctx);
      each_1_lookup.set(key, each_blocks[i] = create_each_block(key, child_ctx));
    }
    let each_1_else = null;
    if (!each_value.length) {
      each_1_else = create_else_block_2(ctx);
    }
    const if_block_creators = [create_if_block_1, create_else_block_1];
    const if_blocks = [];
    function select_block_type(ctx2, dirty) {
      if (
        /*couponValid*/
        ctx2[5]
      ) return 0;
      return 1;
    }
    current_block_type_index = select_block_type(ctx, [-1, -1]);
    if_block0 = if_blocks[current_block_type_index] = if_block_creators[current_block_type_index](ctx);
    function select_block_type_1(ctx2, dirty) {
      if (
        /*giftWrap*/
        ctx2[2]
      ) return create_if_block;
      return create_else_block;
    }
    let current_block_type = select_block_type_1(ctx, [-1, -1]);
    let if_block1 = current_block_type(ctx);
    return {
      c() {
        div13 = element("div");
        div0 = element("div");
        div0.textContent = "Order builder: keyed each, stores, $: derived values";
        t1 = space();
        button0 = element("button");
        t2 = text("Add product");
        t3 = space();
        div1 = element("div");
        t4 = text(
          /*$itemCount*/
          ctx[9]
        );
        t5 = text(" item");
        t6 = text(t6_value);
        t7 = text(", subtotal $");
        t8 = text(
          /*subtotal*/
          ctx[4]
        );
        t9 = space();
        for (let i = 0; i < each_blocks.length; i += 1) {
          each_blocks[i].c();
        }
        if (each_1_else) {
          each_1_else.c();
        }
        t10 = space();
        div2 = element("div");
        div2.textContent = "bind:value + reactive validation";
        t12 = space();
        div3 = element("div");
        div3.textContent = "Coupon";
        t14 = space();
        input0 = element("input");
        t15 = space();
        div4 = element("div");
        t16 = space();
        if_block0.c();
        t17 = space();
        div5 = element("div");
        div5.textContent = "select bind:value, checkbox bind:checked, if block";
        t19 = space();
        select = element("select");
        option0 = element("option");
        option0.textContent = "standard";
        option1 = element("option");
        option1.textContent = "express";
        option2 = element("option");
        option2.textContent = "pickup";
        t23 = space();
        div6 = element("div");
        t24 = text("shipping: ");
        t25 = text(
          /*shipping*/
          ctx[1]
        );
        t26 = text(" ($");
        t27 = text(t27_value);
        t28 = text(")");
        t29 = space();
        input1 = element("input");
        t30 = space();
        div7 = element("div");
        if_block1.c();
        t31 = space();
        div8 = element("div");
        div8.textContent = "svelte/motion tweened checkout";
        t33 = space();
        div9 = element("div");
        t34 = text("Total: $");
        t35 = text(
          /*total*/
          ctx[8]
        );
        t36 = space();
        button1 = element("button");
        t37 = text("Checkout");
        t38 = space();
        button2 = element("button");
        button2.textContent = "Reset";
        t40 = space();
        div11 = element("div");
        div10 = element("div");
        t41 = space();
        div12 = element("div");
        t42 = text(t42_value);
        attr(div0, "class", "card fw-label");
        set_style(div0, "left", "16px");
        set_style(div0, "top", "48px");
        set_style(div0, "width", "448px");
        set_style(div0, "height", "20px");
        attr(button0, "id", "svelteAdd");
        attr(button0, "class", "fw-btn");
        set_style(button0, "left", "16px");
        set_style(button0, "top", "74px");
        set_style(button0, "width", "120px");
        set_style(button0, "height", "24px");
        button0.disabled = button0_disabled_value = /*$cart*/
        ctx[6].length >= 5;
        attr(div1, "class", "fw-note");
        set_style(div1, "left", "148px");
        set_style(div1, "top", "76px");
        set_style(div1, "width", "316px");
        set_style(div1, "height", "20px");
        attr(div2, "class", "card fw-label");
        set_style(div2, "left", "496px");
        set_style(div2, "top", "48px");
        set_style(div2, "width", "448px");
        set_style(div2, "height", "20px");
        attr(div3, "class", "fw-note");
        set_style(div3, "left", "496px");
        set_style(div3, "top", "76px");
        set_style(div3, "width", "60px");
        set_style(div3, "height", "20px");
        attr(input0, "id", "svelteCoupon");
        attr(input0, "class", "fw-input");
        attr(input0, "type", "text");
        set_style(input0, "left", "560px");
        set_style(input0, "top", "74px");
        set_style(input0, "width", "140px");
        set_style(input0, "height", "24px");
        attr(div4, "class", "fw-swatch");
        set_style(div4, "left", "708px");
        set_style(div4, "top", "79px");
        set_style(div4, "width", "14px");
        set_style(div4, "height", "14px");
        toggle_class(
          div4,
          "ok",
          /*couponValid*/
          ctx[5]
        );
        toggle_class(
          div4,
          "bad",
          /*coupon*/
          ctx[0] !== "" && !/*couponValid*/
          ctx[5]
        );
        attr(div5, "class", "card fw-label");
        set_style(div5, "left", "496px");
        set_style(div5, "top", "112px");
        set_style(div5, "width", "448px");
        set_style(div5, "height", "20px");
        option0.__value = "standard";
        set_input_value(option0, option0.__value);
        option1.__value = "express";
        set_input_value(option1, option1.__value);
        option2.__value = "pickup";
        set_input_value(option2, option2.__value);
        attr(select, "id", "svelteShipping");
        attr(select, "class", "fw-select");
        set_style(select, "left", "496px");
        set_style(select, "top", "138px");
        set_style(select, "width", "140px");
        set_style(select, "height", "24px");
        if (
          /*shipping*/
          ctx[1] === void 0
        ) add_render_callback(() => (
          /*select_change_handler*/
          ctx[24].call(select)
        ));
        attr(div6, "class", "fw-note");
        set_style(div6, "left", "648px");
        set_style(div6, "top", "140px");
        set_style(div6, "width", "290px");
        set_style(div6, "height", "20px");
        attr(input1, "id", "svelteGift");
        attr(input1, "type", "checkbox");
        attr(input1, "class", "fw-check");
        set_style(input1, "left", "496px");
        set_style(input1, "top", "174px");
        set_style(input1, "width", "16px");
        set_style(input1, "height", "16px");
        attr(div7, "class", "fw-note");
        set_style(div7, "left", "520px");
        set_style(div7, "top", "172px");
        set_style(div7, "width", "420px");
        set_style(div7, "height", "20px");
        attr(div8, "class", "card fw-label");
        set_style(div8, "left", "496px");
        set_style(div8, "top", "208px");
        set_style(div8, "width", "448px");
        set_style(div8, "height", "20px");
        attr(div9, "class", "fw-note");
        set_style(div9, "left", "496px");
        set_style(div9, "top", "236px");
        set_style(div9, "width", "200px");
        set_style(div9, "height", "20px");
        attr(button1, "id", "svelteCheckout");
        attr(button1, "class", "fw-btn");
        set_style(button1, "left", "704px");
        set_style(button1, "top", "234px");
        set_style(button1, "width", "110px");
        set_style(button1, "height", "24px");
        button1.disabled = button1_disabled_value = /*checkedOut*/
        ctx[7] || /*$cart*/
        ctx[6].length === 0;
        attr(button2, "id", "svelteReset");
        attr(button2, "class", "fw-btn");
        set_style(button2, "left", "822px");
        set_style(button2, "top", "234px");
        set_style(button2, "width", "80px");
        set_style(button2, "height", "24px");
        attr(div10, "id", "svelteProgress");
        attr(div10, "class", "fw-fill");
        set_style(div10, "left", "0px");
        set_style(div10, "top", "0px");
        set_style(div10, "width", Math.round(444 * /*$progress*/
        ctx[10]) + "px");
        set_style(div10, "height", "10px");
        attr(div11, "class", "fw-track");
        set_style(div11, "left", "496px");
        set_style(div11, "top", "268px");
        set_style(div11, "width", "444px");
        set_style(div11, "height", "10px");
        attr(div12, "class", "fw-note");
        set_style(div12, "left", "496px");
        set_style(div12, "top", "284px");
        set_style(div12, "width", "444px");
        set_style(div12, "height", "20px");
        attr(div13, "id", "svelteApp");
      },
      m(target, anchor) {
        insert(target, div13, anchor);
        append(div13, div0);
        append(div13, t1);
        append(div13, button0);
        append(button0, t2);
        append(div13, t3);
        append(div13, div1);
        append(div1, t4);
        append(div1, t5);
        append(div1, t6);
        append(div1, t7);
        append(div1, t8);
        append(div13, t9);
        for (let i = 0; i < each_blocks.length; i += 1) {
          if (each_blocks[i]) {
            each_blocks[i].m(div13, null);
          }
        }
        if (each_1_else) {
          each_1_else.m(div13, null);
        }
        append(div13, t10);
        append(div13, div2);
        append(div13, t12);
        append(div13, div3);
        append(div13, t14);
        append(div13, input0);
        set_input_value(
          input0,
          /*coupon*/
          ctx[0]
        );
        append(div13, t15);
        append(div13, div4);
        append(div13, t16);
        if_blocks[current_block_type_index].m(div13, null);
        append(div13, t17);
        append(div13, div5);
        append(div13, t19);
        append(div13, select);
        append(select, option0);
        append(select, option1);
        append(select, option2);
        select_option(
          select,
          /*shipping*/
          ctx[1],
          true
        );
        append(div13, t23);
        append(div13, div6);
        append(div6, t24);
        append(div6, t25);
        append(div6, t26);
        append(div6, t27);
        append(div6, t28);
        append(div13, t29);
        append(div13, input1);
        input1.checked = /*giftWrap*/
        ctx[2];
        append(div13, t30);
        append(div13, div7);
        if_block1.m(div7, null);
        append(div13, t31);
        append(div13, div8);
        append(div13, t33);
        append(div13, div9);
        append(div9, t34);
        append(div9, t35);
        append(div13, t36);
        append(div13, button1);
        append(button1, t37);
        append(div13, t38);
        append(div13, button2);
        append(div13, t40);
        append(div13, div11);
        append(div11, div10);
        append(div13, t41);
        append(div13, div12);
        append(div12, t42);
        if (!mounted) {
          dispose = [
            listen(
              button0,
              "click",
              /*addProduct*/
              ctx[13]
            ),
            listen(
              input0,
              "input",
              /*input0_input_handler*/
              ctx[23]
            ),
            listen(
              select,
              "change",
              /*select_change_handler*/
              ctx[24]
            ),
            listen(
              input1,
              "change",
              /*input1_change_handler*/
              ctx[25]
            ),
            listen(
              button1,
              "click",
              /*checkout*/
              ctx[18]
            ),
            listen(
              button2,
              "click",
              /*reset*/
              ctx[19]
            )
          ];
          mounted = true;
        }
      },
      p(ctx2, dirty) {
        if (dirty[0] & /*$cart*/
        64 && button0_disabled_value !== (button0_disabled_value = /*$cart*/
        ctx2[6].length >= 5)) {
          button0.disabled = button0_disabled_value;
        }
        if (dirty[0] & /*$itemCount*/
        512) set_data(
          t4,
          /*$itemCount*/
          ctx2[9]
        );
        if (dirty[0] & /*$itemCount*/
        512 && t6_value !== (t6_value = /*$itemCount*/
        ctx2[9] === 1 ? "" : "s")) set_data(t6, t6_value);
        if (dirty[0] & /*subtotal*/
        16) set_data(
          t8,
          /*subtotal*/
          ctx2[4]
        );
        if (dirty[0] & /*$cart, remove, bump*/
        49216) {
          each_value = ensure_array_like(
            /*$cart*/
            ctx2[6]
          );
          each_blocks = update_keyed_each(each_blocks, dirty, get_key, 1, ctx2, each_value, each_1_lookup, div13, destroy_block, create_each_block, t10, get_each_context);
          if (!each_value.length && each_1_else) {
            each_1_else.p(ctx2, dirty);
          } else if (!each_value.length) {
            each_1_else = create_else_block_2(ctx2);
            each_1_else.c();
            each_1_else.m(div13, t10);
          } else if (each_1_else) {
            each_1_else.d(1);
            each_1_else = null;
          }
        }
        if (dirty[0] & /*coupon*/
        1 && input0.value !== /*coupon*/
        ctx2[0]) {
          set_input_value(
            input0,
            /*coupon*/
            ctx2[0]
          );
        }
        if (dirty[0] & /*couponValid*/
        32) {
          toggle_class(
            div4,
            "ok",
            /*couponValid*/
            ctx2[5]
          );
        }
        if (dirty[0] & /*coupon, couponValid*/
        33) {
          toggle_class(
            div4,
            "bad",
            /*coupon*/
            ctx2[0] !== "" && !/*couponValid*/
            ctx2[5]
          );
        }
        let previous_block_index = current_block_type_index;
        current_block_type_index = select_block_type(ctx2, dirty);
        if (current_block_type_index === previous_block_index) {
          if_blocks[current_block_type_index].p(ctx2, dirty);
        } else {
          group_outros();
          transition_out(if_blocks[previous_block_index], 1, 1, () => {
            if_blocks[previous_block_index] = null;
          });
          check_outros();
          if_block0 = if_blocks[current_block_type_index];
          if (!if_block0) {
            if_block0 = if_blocks[current_block_type_index] = if_block_creators[current_block_type_index](ctx2);
            if_block0.c();
          } else {
            if_block0.p(ctx2, dirty);
          }
          transition_in(if_block0, 1);
          if_block0.m(div13, t17);
        }
        if (dirty[0] & /*shipping*/
        2) {
          select_option(
            select,
            /*shipping*/
            ctx2[1]
          );
        }
        if (dirty[0] & /*shipping*/
        2) set_data(
          t25,
          /*shipping*/
          ctx2[1]
        );
        if (dirty[0] & /*shipping*/
        2 && t27_value !== (t27_value = /*SHIPPING*/
        ctx2[16][
          /*shipping*/
          ctx2[1]
        ] + "")) set_data(t27, t27_value);
        if (dirty[0] & /*giftWrap*/
        4) {
          input1.checked = /*giftWrap*/
          ctx2[2];
        }
        if (current_block_type !== (current_block_type = select_block_type_1(ctx2, dirty))) {
          if_block1.d(1);
          if_block1 = current_block_type(ctx2);
          if (if_block1) {
            if_block1.c();
            if_block1.m(div7, null);
          }
        }
        if (dirty[0] & /*total*/
        256) set_data(
          t35,
          /*total*/
          ctx2[8]
        );
        if (dirty[0] & /*checkedOut, $cart*/
        192 && button1_disabled_value !== (button1_disabled_value = /*checkedOut*/
        ctx2[7] || /*$cart*/
        ctx2[6].length === 0)) {
          button1.disabled = button1_disabled_value;
        }
        if (dirty[0] & /*$progress*/
        1024) {
          set_style(div10, "width", Math.round(444 * /*$progress*/
          ctx2[10]) + "px");
        }
        if (dirty[0] & /*checkedOut, $progress*/
        1152 && t42_value !== (t42_value = /*checkedOut*/
        ctx2[7] ? (
          /*$progress*/
          ctx2[10] >= 1 ? "Order placed." : "Placing order... " + Math.round(
            /*$progress*/
            ctx2[10] * 100
          ) + "%"
        ) : "Not checked out")) set_data(t42, t42_value);
      },
      i(local) {
        transition_in(if_block0);
      },
      o(local) {
        transition_out(if_block0);
      },
      d(detaching) {
        if (detaching) {
          detach(div13);
        }
        for (let i = 0; i < each_blocks.length; i += 1) {
          each_blocks[i].d();
        }
        if (each_1_else) each_1_else.d();
        if_blocks[current_block_type_index].d();
        if_block1.d();
        mounted = false;
        run_all(dispose);
      }
    };
  }
  var ROW_TOP = 106;
  var ROW_STEP = 30;
  var BAR_UNIT = 14;
  var MAX_QTY = 6;
  function instance($$self, $$props, $$invalidate) {
    let couponValid;
    let subtotal;
    let discount;
    let total;
    let $cart;
    let $itemCount;
    let $progress;
    const CATALOGUE = [
      {
        name: "Keyboard",
        price: 40,
        color: "rgb(230, 70, 70)"
      },
      {
        name: "Mouse",
        price: 15,
        color: "rgb(80, 200, 120)"
      },
      {
        name: "Monitor",
        price: 120,
        color: "rgb(70, 130, 220)"
      },
      {
        name: "Headset",
        price: 60,
        color: "rgb(160, 90, 220)"
      },
      {
        name: "Webcam",
        price: 35,
        color: "rgb(240, 160, 40)"
      }
    ];
    const cart = writable([{ id: 1, ...CATALOGUE[0], qty: 1 }, { id: 2, ...CATALOGUE[1], qty: 2 }]);
    component_subscribe($$self, cart, (value) => $$invalidate(6, $cart = value));
    const itemCount = derived(cart, ($c) => $c.reduce((n, it) => n + it.qty, 0));
    component_subscribe($$self, itemCount, (value) => $$invalidate(9, $itemCount = value));
    let nextId = 3;
    let nextProduct = 2;
    function addProduct() {
      if ($cart.length >= 5) return;
      const p = CATALOGUE[nextProduct % CATALOGUE.length];
      nextProduct += 1;
      cart.update((c) => [...c, { id: nextId++, ...p, qty: 1 }]);
    }
    function bump(id, delta) {
      cart.update((c) => c.map((it) => it.id === id ? {
        ...it,
        qty: Math.max(1, Math.min(MAX_QTY, it.qty + delta))
      } : it));
    }
    function remove(id) {
      cart.update((c) => c.filter((it) => it.id !== id));
    }
    let coupon = "";
    let shipping = "standard";
    let giftWrap = false;
    const SHIPPING = { standard: 5, express: 15, pickup: 0 };
    const progress = tweened(0, { duration: 800, easing: cubicOut });
    component_subscribe($$self, progress, (value) => $$invalidate(10, $progress = value));
    let checkedOut = false;
    function checkout() {
      $$invalidate(7, checkedOut = true);
      progress.set(1);
    }
    function reset() {
      $$invalidate(7, checkedOut = false);
      progress.set(0, { duration: 0 });
    }
    const click_handler = (it) => bump(it.id, -1);
    const click_handler_1 = (it) => bump(it.id, 1);
    const click_handler_2 = (it) => remove(it.id);
    function input0_input_handler() {
      coupon = this.value;
      $$invalidate(0, coupon);
    }
    function select_change_handler() {
      shipping = select_value(this);
      $$invalidate(1, shipping);
    }
    function input1_change_handler() {
      giftWrap = this.checked;
      $$invalidate(2, giftWrap);
    }
    $$self.$$.update = () => {
      if ($$self.$$.dirty[0] & /*coupon*/
      1) {
        $: $$invalidate(5, couponValid = /^[A-Z]{4}\d{2}$/.test(coupon));
      }
      if ($$self.$$.dirty[0] & /*$cart*/
      64) {
        $: $$invalidate(4, subtotal = $cart.reduce((s, it) => s + it.price * it.qty, 0));
      }
      if ($$self.$$.dirty[0] & /*couponValid, subtotal*/
      48) {
        $: $$invalidate(3, discount = couponValid ? Math.round(subtotal * 0.1) : 0);
      }
      if ($$self.$$.dirty[0] & /*subtotal, discount, shipping, giftWrap*/
      30) {
        $: $$invalidate(8, total = subtotal - discount + SHIPPING[shipping] + (giftWrap ? 3 : 0));
      }
    };
    return [
      coupon,
      shipping,
      giftWrap,
      discount,
      subtotal,
      couponValid,
      $cart,
      checkedOut,
      total,
      $itemCount,
      $progress,
      cart,
      itemCount,
      addProduct,
      bump,
      remove,
      SHIPPING,
      progress,
      checkout,
      reset,
      click_handler,
      click_handler_1,
      click_handler_2,
      input0_input_handler,
      select_change_handler,
      input1_change_handler
    ];
  }
  var Showcase = class extends SvelteComponent {
    constructor(options) {
      super();
      init(this, options, instance, create_fragment, safe_not_equal, {}, null, [-1, -1]);
    }
  };
  var Showcase_default = Showcase;

  // src/main.js
  new Showcase_default({ target: document.getElementById("svelteRoot") });
})();
