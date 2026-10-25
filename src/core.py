"""systemd-style unit management for SigmaOS-systemd.

Principles: pure plan / thin execute (enable computes a symlink plan before
applying it into an isolated store -- self_test never touches the real
/system), fail-fast on dependency cycles and missing ExecStart, deterministic
ordering, least astonishment (status words are explicit).
"""
import argparse, json, os, re, shutil, sys

ENGINE = {
    "name": "sigma-unit",
    "summary": "Enable, start and inspect service units (isolated store)",
    "language": "python",
    "verbs": ["enable", "disable", "start", "status", "cat"],
    "principles": ["Pure Plan / Thin Execute", "Fail-Fast",
                   "Deterministic Testing", "KISS", "Information Hiding"],
}

cli_doc = """\
$ sigma-unit --store ./store enable sshd.service
$ sigma-unit --store ./store start sshd.service
$ sigma-unit --store ./store status sshd.service
$ sigma-unit --store ./store cat sshd.service
"""

_UNIT_RE = re.compile(r"^[A-Za-z0-9_.@-]+\.(service|target|socket)$")
_STATE = ("started", "stopped")


class UnitError(Exception):
    pass


def parse_unit(text, name="<unit>"):
    """Pure: parse INI-style unit text into a structured dict."""
    unit, section = {}, None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if section not in ("Unit", "Service", "Install"):
                raise UnitError(f"{name}: line {lineno}: unknown section {line}")
            continue
        if "=" not in line:
            raise UnitError(f"{name}: line {lineno}: expected Key=Value: {line!r}")
        key, _, value = line.partition("=")
        key = key.strip()
        if section is None:
            raise UnitError(f"{name}: line {lineno}: key outside any section")
        if section == "Unit" and key == "Description":
            unit["description"] = value.strip()
        elif section == "Unit" and key in ("Wants", "Requires", "After"):
            unit[key.lower()] = value.split()
        elif section == "Service" and key == "ExecStart":
            unit["exec_start"] = value.strip()
        elif section == "Service" and key == "Type":
            unit["type"] = value.strip()
        elif section == "Install" and key == "WantedBy":
            unit["wanted_by"] = value.split()
        # unknown keys are ignored (forward compatibility)
    for req in ("exec_start",):
        if not unit.get(req):
            raise UnitError(f"{name}: missing {req}")
    if unit.get("type") is None:
        unit["type"] = "simple"
    return unit


def load_unit(store, name):
    if not _UNIT_RE.match(name):
        raise UnitError(f"bad unit name: {name!r}")
    path = os.path.join(store, "units", name)
    if not os.path.isfile(path):
        raise UnitError(f"no such unit: {name}")
    with open(path, "r", encoding="utf-8") as fh:
        unit = parse_unit(fh.read(), name=name)
    unit["name"] = name
    return unit


def enable_plan(store, unit):
    """Pure: compute the WantedBy symlink paths an enable would create."""
    targets = unit.get("wanted_by", [])
    if not targets:
        raise UnitError(f"{unit['name']}: no WantedBy= target; cannot enable")
    return [os.path.join(store, "links", f"{t}.wants", unit["name"])
            for t in sorted(targets)]


def _apply_links(store, unit, links, enabled=True):
    """Thin execute layer: only ever touches the isolated store."""
    created = []
    for link in links:
        if enabled:
            os.makedirs(os.path.dirname(link), exist_ok=True)
            if not os.path.exists(link):
                with open(link, "w", encoding="utf-8") as fh:
                    fh.write(unit["name"] + "\n")
                created.append(link)
        elif os.path.exists(link):
            os.remove(link)
            created.append(link)
    return created


def enable(store, unit):
    links = enable_plan(store, unit)
    created = _apply_links(store, unit, links, enabled=True)
    return {"planned": links, "created": created}


def disable(store, unit):
    links = [os.path.join(store, "links", f"{t}.wants", unit["name"])
             for t in sorted(unit.get("wanted_by", []))]
    removed = _apply_links(store, unit, links, enabled=False)
    return {"planned": links, "removed": removed}


def _state_path(store):
    return os.path.join(store, "state.json")


def _read_state(store):
    if not os.path.exists(_state_path(store)):
        return {}
    with open(_state_path(store), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_state(store, state):
    os.makedirs(store, exist_ok=True)
    tmp = _state_path(store) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, _state_path(store))


def start(store, name):
    """Plan + apply in isolated store: topologically start unit and deps."""
    units = _load_all(store)
    if name not in units:
        raise UnitError(f"no such unit: {name}")
    chain = _closure(units, name)
    order = _topo({n: units[n] for n in chain})   # only the unit's own graph
    started = []
    state = _read_state(store)
    for n in order:
        if state.get(n) != "started":
            state[n] = "started"
            started.append(n)
    state[name] = "started"
    if name not in started:
        started.append(name)
    _write_state(store, state)
    return started


def stop(store, name):
    state = _read_state(store)
    if name not in state:
        raise UnitError(f"unit not active: {name}")
    state[name] = "stopped"
    _write_state(store, state)
    return state[name]


def status(store, name):
    if name not in _load_unit_names(store):
        raise UnitError(f"no such unit: {name}")
    return _read_state(store).get(name, "stopped")


def _load_unit_names(store):
    units_dir = os.path.join(store, "units")
    if not os.path.isdir(units_dir):
        raise UnitError(f"store has no units directory: {units_dir}")
    return sorted(os.listdir(units_dir))


def _load_all(store):
    return {name: load_unit(store, name) for name in _load_unit_names(store)}


def _topo(units):
    indeg = {n: len(u.get("wants", [])) for n, u in units.items()}
    dependents = {n: [] for n in units}
    for n, u in units.items():
        for dep in u.get("wants", []):
            if dep not in units:
                raise UnitError(f"{n}: unknown dependency {dep!r}")
            dependents[dep].append(n)
    ready = sorted(n for n, d in indeg.items() if d == 0)
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in sorted(dependents[n]):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort()
    if len(order) != len(units):
        cyclic = sorted(n for n, d in indeg.items() if d > 0)
        raise UnitError("dependency cycle: " + ", ".join(cyclic))
    return order


def _closure(units, name):
    seen = set()

    def add(n):
        if n in seen:
            return
        seen.add(n)
        for dep in units[n].get("wants", []):
            if dep not in units:
                raise UnitError(f"{n}: unknown dependency {dep!r}")
            add(dep)

    add(name)
    return seen


def cat_unit(store, name):
    path = os.path.join(store, "units", name)
    if not _UNIT_RE.match(name) or not os.path.isfile(path):
        raise UnitError(f"no such unit: {name}")
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_unit(store, name, text):
    """Helper: install a unit file into the isolated store."""
    if not _UNIT_RE.match(name):
        raise UnitError(f"bad unit name: {name!r}")
    parse_unit(text, name=name)  # fail-fast: reject bad unit text
    os.makedirs(os.path.join(store, "units"), exist_ok=True)
    path = os.path.join(store, "units", name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=ENGINE["name"], description=ENGINE["summary"])
    p.add_argument("--store", default="./sigma-unit-store",
                   help="isolated unit store directory")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("enable", help="plan + apply WantedBy links")
    e.add_argument("unit")
    d = sub.add_parser("disable", help="remove WantedBy links")
    d.add_argument("unit")
    s = sub.add_parser("start", help="start unit and its dependencies")
    s.add_argument("unit")
    st = sub.add_parser("status", help="show unit state")
    st.add_argument("unit")
    c = sub.add_parser("cat", help="print the unit file")
    c.add_argument("unit")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        unit = None
        if args.cmd in ("enable", "disable"):
            unit = load_unit(args.store, args.unit)
        if args.cmd == "enable":
            res = enable(args.store, unit)
            for link in res["planned"]:
                print(f"link {link}")
            print(f"enabled {args.unit} ({len(res['planned'])} link(s))")
        elif args.cmd == "disable":
            res = disable(args.store, unit)
            print(f"disabled {args.unit} ({len(res['removed'])} link(s) removed)")
        elif args.cmd == "start":
            for n in start(args.store, args.unit):
                print(f"started {n}")
        elif args.cmd == "status":
            print(status(args.store, args.unit))
        elif args.cmd == "cat":
            sys.stdout.write(cat_unit(args.store, args.unit))
        return 0
    except (UnitError, OSError, ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as store:
        write_unit(store, "networkd.service",
                   "[Unit]\nDescription=Network daemon\n"
                   "[Service]\nExecStart=/usr/lib/sigma-networkd\n"
                   "[Install]\nWantedBy=multi-user.target\n")
        write_unit(store, "sshd.service",
                   "[Unit]\nDescription=SSH server\nWants=networkd.service\n"
                   "After=networkd.service\n"
                   "[Service]\nExecStart=/usr/sbin/sshd -D\nType=simple\n"
                   "[Install]\nWantedBy=multi-user.target\n")
        # parse
        u = load_unit(store, "sshd.service")
        assert u["exec_start"] == "/usr/sbin/sshd -D"
        assert u["wants"] == ["networkd.service"]
        assert u["wanted_by"] == ["multi-user.target"]
        assert u["type"] == "simple"
        # enable: pure plan, then apply into isolated store
        n = load_unit(store, "networkd.service")
        plan = enable_plan(store, n)
        assert plan == [os.path.join(store, "links", "multi-user.target.wants",
                                     "networkd.service")]
        res = enable(store, n)
        assert res["created"] == plan and os.path.isfile(plan[0])
        assert enable(store, n)["created"] == []        # idempotent
        # start: dependency order in an isolated store
        order = start(store, "sshd.service")
        assert order.index("networkd.service") < order.index("sshd.service")
        assert status(store, "sshd.service") == "started"
        assert status(store, "networkd.service") == "started"
        # stop / status transition
        assert stop(store, "sshd.service") == "stopped"
        assert status(store, "sshd.service") == "stopped"
        # disable removes the link
        dis = disable(store, n)
        assert dis["removed"] == plan and not os.path.exists(plan[0])
        # cat returns the original text
        assert "ExecStart=/usr/sbin/sshd -D" in cat_unit(store, "sshd.service")
        # fail-fast
        write_unit(store, "loopa.service",
                   "[Unit]\nDescription=a\nWants=loopb.service\n"
                   "[Service]\nExecStart=/bin/true\n")
        write_unit(store, "loopb.service",
                   "[Unit]\nDescription=b\nWants=loopa.service\n"
                   "[Service]\nExecStart=/bin/true\n")
        try:
            start(store, "loopa.service")
        except UnitError as e:
            assert "cycle" in str(e)
        else:
            raise AssertionError("cycle not detected")
        try:
            enable(store, load_unit(store, "loopa.service"))  # no WantedBy
        except UnitError as e:
            assert "WantedBy" in str(e)
        else:
            raise AssertionError("enable without WantedBy not rejected")
        for bad_call in (
            lambda: load_unit(store, "bad name.service"),
            lambda: load_unit(store, "ghost.service"),
            lambda: parse_unit("Description=outside\n[Service]\nExecStart=/bin/true\n"),
            lambda: parse_unit("[Service]\nType=simple\n"),
            lambda: parse_unit("[Nope]\nExecStart=/bin/true\n"),
            lambda: parse_unit("[Service]\nExecStart\n"),
            lambda: stop(store, "ghost.service"),
            lambda: status(store, "ghost.service"),
            lambda: start(store, "ghost.service"),
        ):
            try:
                bad_call()
            except UnitError:
                pass
            else:
                raise AssertionError("expected UnitError")
        # CLI smoke through main()
        assert main(["--store", store, "cat", "sshd.service"]) == 0
        assert main(["--store", store, "enable", "sshd.service"]) == 0
        assert main(["--store", store, "start", "sshd.service"]) == 0
        assert main(["--store", store, "status", "sshd.service"]) == 0
        assert main(["--store", store, "disable", "sshd.service"]) == 0
        assert main(["--store", store, "cat", "ghost.service"]) == 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
