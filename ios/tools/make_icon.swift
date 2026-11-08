// Renders the 1024x1024 app icon. Drawn with an alpha channel (AppKit needs one), then flattened to opaque.
// Usage: swift ios/tools/make_icon.swift ios/BTCDaily/Assets.xcassets/AppIcon.appiconset/AppIcon.png
import AppKit

let size = 1024
let out = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "AppIcon.png"
guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size, bitsPerSample: 8,
                                 samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                 colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { exit(1) }
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let rect = NSRect(x: 0, y: 0, width: size, height: size)

// dark background with a warm glow, like the dashboard header
NSGradient(starting: NSColor(red: 0.09, green: 0.09, blue: 0.10, alpha: 1),
           ending: NSColor(red: 0.05, green: 0.05, blue: 0.06, alpha: 1))!.draw(in: rect, angle: -90)
NSGradient(colors: [NSColor(red: 0.97, green: 0.58, blue: 0.10, alpha: 0.38), NSColor(red: 0.97, green: 0.58, blue: 0.10, alpha: 0)])!
    .draw(fromCenter: NSPoint(x: 780, y: 860), radius: 0, toCenter: NSPoint(x: 780, y: 860), radius: 760, options: [])

// orange rounded tile with the ₿ mark
let tile = NSRect(x: 212, y: 212, width: 600, height: 600)
let path = NSBezierPath(roundedRect: tile, xRadius: 150, yRadius: 150)
NSGradient(starting: NSColor(red: 1.0, green: 0.71, blue: 0.29, alpha: 1),
           ending: NSColor(red: 0.85, green: 0.47, blue: 0.02, alpha: 1))!.draw(in: path, angle: -55)
let style = NSMutableParagraphStyle(); style.alignment = .center
let glyph = NSAttributedString(string: "₿", attributes: [
    .font: NSFont.systemFont(ofSize: 430, weight: .heavy),
    .foregroundColor: NSColor(red: 0.10, green: 0.07, blue: 0.02, alpha: 1),
    .paragraphStyle: style,
])
let g = glyph.size()
glyph.draw(in: NSRect(x: tile.minX, y: tile.midY - g.height / 2 - 6, width: tile.width, height: g.height))

NSGraphicsContext.restoreGraphicsState()
// flatten: copy into an opaque CGImage so the PNG has no alpha channel (iOS icon requirement)
let cs = CGColorSpaceCreateDeviceRGB()
let ctx = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                    bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
ctx.draw(rep.cgImage!, in: CGRect(x: 0, y: 0, width: size, height: size))
let opaque = NSBitmapImageRep(cgImage: ctx.makeImage()!)
try! opaque.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: out))
print("wrote \(out)")
