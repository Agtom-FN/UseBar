// UseBar (macOS) — menu-bar usage readout for Claude Code and Cursor.
//
// Thin GUI over the shared Python engine: runs `run.py` (bundled in Resources),
// renders the unified JSON contract (bar text + metric rows), and lets the user
// pick which service to show. No pip dependencies — the engines are stdlib only.

import AppKit
import Foundation

// MARK: - Model (mirrors engines/common.py)

struct Metric {
    var key = ""
    var label = ""
    var short = ""
    var kind = "pct"
    var value: Double?
    var maximum: Double?
    var resetsAt: Date?
    var severity: String?

    func rendered() -> String {
        guard let v = value else { return "–" }
        switch kind {
        case "ratio": return maximum.map { "\(Int(v))/\(Int($0))" } ?? "\(Int(v))"
        case "count": return human(v)
        default: return String(format: "%.0f%%", v)
        }
    }
}

struct EngineResult {
    var service = "claude"
    var ok = false
    var error: String?
    var note: String?
    var bar = ""
    var metrics: [Metric] = []
}

// MARK: - Helpers

func human(_ n: Double) -> String {
    if n >= 1_000_000_000 { return String(format: "%.2fB", n / 1_000_000_000) }
    if n >= 1_000_000 { return String(format: "%.1fM", n / 1_000_000) }
    if n >= 1_000 { return String(format: "%.1fK", n / 1_000) }
    return "\(Int(n))"
}

func parseISO(_ s: String?) -> Date? {
    guard let s = s else { return nil }
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if let d = f.date(from: s) { return d }
    f.formatOptions = [.withInternetDateTime]
    return f.date(from: s)
}

func resetText(_ d: Date?) -> String {
    guard let d = d else { return "" }
    let f = DateFormatter(); f.dateFormat = "EEE HH:mm"
    return " · resets \(f.string(from: d))"
}

// MARK: - Icons (drawn as template images so they adapt to light/dark)

func claudeIcon() -> NSImage {
    let size = NSSize(width: 18, height: 18)
    let img = NSImage(size: size)
    img.lockFocus()
    let c = NSPoint(x: size.width / 2, y: size.height / 2)
    NSColor.black.setFill()
    let rays = 12
    let rOuter: CGFloat = 8.4
    let rInner: CGFloat = 1.1
    let wInner: CGFloat = 1.7   // ray thickness at hub
    for i in 0..<rays {
        let a = (CGFloat(i) / CGFloat(rays)) * 2 * .pi
        let ca = cos(a), sa = sin(a)
        // perpendicular for thickness
        let px = -sa, py = ca
        let tip = NSPoint(x: c.x + ca * rOuter, y: c.y + sa * rOuter)
        let b1 = NSPoint(x: c.x + ca * rInner + px * wInner, y: c.y + sa * rInner + py * wInner)
        let b2 = NSPoint(x: c.x + ca * rInner - px * wInner, y: c.y + sa * rInner - py * wInner)
        let p = NSBezierPath()
        p.move(to: tip); p.line(to: b1); p.line(to: b2); p.close()
        p.fill()
    }
    // small hub
    NSBezierPath(ovalIn: NSRect(x: c.x - 1.6, y: c.y - 1.6, width: 3.2, height: 3.2)).fill()
    img.unlockFocus()
    img.isTemplate = true
    return img
}

func cursorIcon() -> NSImage {
    if let sym = NSImage(systemSymbolName: "cursorarrow", accessibilityDescription: "Cursor") {
        sym.isTemplate = true
        return sym
    }
    let img = NSImage(size: NSSize(width: 14, height: 14))
    img.lockFocus(); NSColor.black.setFill()
    let p = NSBezierPath()
    p.move(to: NSPoint(x: 2, y: 12)); p.line(to: NSPoint(x: 2, y: 2))
    p.line(to: NSPoint(x: 9, y: 9)); p.close(); p.fill()
    img.unlockFocus(); img.isTemplate = true
    return img
}

// MARK: - Controller

final class AppController: NSObject {
    let statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var timer: Timer?
    let dir: String
    let python: String
    var currentService = "claude"
    var services = ["claude", "cursor"]
    var betaServices: Set<String> = ["cursor"]

    func displayName(_ s: String) -> String {
        let base = s == "cursor" ? "Cursor" : "Claude"
        return betaServices.contains(s) ? "\(base) (beta)" : base
    }

    override init() {
        let fm = FileManager.default
        let home = NSHomeDirectory()
        var cands: [String] = []
        if let r = Bundle.main.resourcePath { cands.append(r) }
        if let e = Bundle.main.executablePath { cands.append((e as NSString).deletingLastPathComponent) }
        cands.append(home + "/UseBar")
        dir = cands.first { fm.fileExists(atPath: $0 + "/run.py") } ?? (home + "/UseBar")
        let py = ["/opt/homebrew/bin/python3", "/usr/bin/python3", "/usr/local/bin/python3"]
        python = py.first { fm.isExecutableFile(atPath: $0) } ?? "/usr/bin/python3"
        super.init()
    }

    func start() {
        if let b = statusItem.button {
            b.title = " …"
            b.imagePosition = .imageLeading
            b.font = NSFont.monospacedDigitSystemFont(ofSize: 12, weight: .medium)
        }
        loadServices()
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 120, repeats: true) { [weak self] _ in self?.refresh() }
    }

    // run.py helpers
    func runPy(_ args: [String]) -> Data {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = [dir + "/run.py"] + args
        let out = Pipe(); p.standardOutput = out; p.standardError = Pipe()
        do { try p.run() } catch { return Data() }
        let d = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return d
    }

    func loadServices() {
        let d = runPy(["--list-services"])
        if let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] {
            if let s = o["services"] as? [String] { services = s }
            if let c = o["current"] as? String { currentService = c }
            if let b = o["beta"] as? [String] { betaServices = Set(b) }
        }
    }

    func selectService(_ s: String) {
        _ = runPy(["--set-service", s])
        currentService = s
        if let b = statusItem.button { b.title = " …" }
        refresh()
    }

    func refresh() {
        DispatchQueue.global(qos: .utility).async { [weak self] in
            guard let self = self else { return }
            let r = self.fetch()
            DispatchQueue.main.async { self.render(r) }
        }
    }

    func fetch() -> EngineResult {
        var r = EngineResult()
        let d = runPy([])
        guard let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else {
            r.error = "engine failed"; return r
        }
        r.service = (o["service"] as? String) ?? currentService
        r.ok = (o["ok"] as? Bool) ?? false
        r.error = o["error"] as? String
        r.note = o["note"] as? String
        r.bar = (o["bar"] as? String) ?? ""
        if let ms = o["metrics"] as? [[String: Any]] {
            r.metrics = ms.map { m in
                var x = Metric()
                x.key = (m["key"] as? String) ?? ""
                x.label = (m["label"] as? String) ?? ""
                x.short = (m["short"] as? String) ?? ""
                x.kind = (m["kind"] as? String) ?? "pct"
                if let v = m["value"] as? Double { x.value = v }
                else if let v = m["value"] as? Int { x.value = Double(v) }
                if let v = m["maximum"] as? Double { x.maximum = v }
                else if let v = m["maximum"] as? Int { x.maximum = Double(v) }
                x.resetsAt = parseISO(m["resets_at"] as? String)
                x.severity = m["severity"] as? String
                return x
            }
        }
        return r
    }

    func render(_ r: EngineResult) {
        if let b = statusItem.button {
            b.image = (r.service == "cursor") ? cursorIcon() : claudeIcon()
            // Build short bar text from metrics (keeps F/U labels the engine set).
            let text = r.metrics.map { "\($0.short) \($0.rendered())" }.joined(separator: "  ")
            b.title = text.isEmpty ? (r.ok ? "" : " ⚠") : " " + text
        }
        statusItem.menu = buildMenu(r)
    }

    func buildMenu(_ r: EngineResult) -> NSMenu {
        let m = NSMenu()
        func header(_ t: String) {
            let i = NSMenuItem(title: t, action: nil, keyEquivalent: "")
            i.attributedTitle = NSAttributedString(string: t, attributes: [.font: NSFont.boldSystemFont(ofSize: 12)])
            m.addItem(i)
        }
        func line(_ t: String) {
            let i = NSMenuItem(title: t, action: nil, keyEquivalent: ""); i.isEnabled = false; m.addItem(i)
        }

        header(displayName(r.service))
        if r.ok {
            for mt in r.metrics {
                line("  \(mt.label): \(mt.rendered())\(resetText(mt.resetsAt))")
            }
            if let n = r.note { line("  \(n)") }
        } else {
            line("  \(r.error ?? "unavailable")")
            if !r.metrics.isEmpty {
                for mt in r.metrics { line("  \(mt.label): \(mt.rendered())") }
            }
        }
        m.addItem(.separator())

        header("Service")
        for s in services {
            let it = NSMenuItem(title: displayName(s), action: #selector(pickService(_:)), keyEquivalent: "")
            it.target = self
            it.representedObject = s
            it.state = (s == currentService) ? .on : .off
            m.addItem(it)
        }
        m.addItem(.separator())

        let refresh = NSMenuItem(title: "Refresh now", action: #selector(doRefresh), keyEquivalent: "r")
        refresh.target = self; m.addItem(refresh)
        let quit = NSMenuItem(title: "Quit UseBar", action: #selector(doQuit), keyEquivalent: "q")
        quit.target = self; m.addItem(quit)
        return m
    }

    @objc func pickService(_ sender: NSMenuItem) {
        if let s = sender.representedObject as? String { selectService(s) }
    }
    @objc func doRefresh() { refresh() }
    @objc func doQuit() { NSApp.terminate(nil) }
}

// MARK: - Entry

final class AppDelegate: NSObject, NSApplicationDelegate {
    let controller: AppController
    init(controller: AppController) { self.controller = controller }
    func applicationDidFinishLaunching(_ n: Notification) { controller.start() }
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let controller = AppController()
let delegate = AppDelegate(controller: controller)
app.delegate = delegate
app.run()
