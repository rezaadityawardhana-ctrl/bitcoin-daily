import SwiftUI

/// Animated bitcoin backdrop: dark gradient, slow-moving orange/blue glows, two chains of blocks drifting
/// in opposite directions, and ₿ symbols floating upward. Drawn with Canvas, so it stays cheap.
struct BTCBackground: View {
    var intensity: Double = 1.0  // 1 = full (splash/empty), lower behind the dashboard

    private static let orange = Color(red: 0.97, green: 0.58, blue: 0.10)
    private static let blue = Color(red: 0.22, green: 0.53, blue: 0.90)

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { timeline in
            let t = timeline.date.timeIntervalSinceReferenceDate
            Canvas { ctx, size in
                let rect = CGRect(origin: .zero, size: size)
                ctx.fill(Path(rect), with: .linearGradient(
                    Gradient(colors: [Color(red: 0.07, green: 0.07, blue: 0.08), Color(red: 0.03, green: 0.03, blue: 0.035)]),
                    startPoint: .zero, endPoint: CGPoint(x: 0, y: size.height)))

                // drifting glows
                glow(&ctx, center: CGPoint(x: size.width * 0.85 + cos(t * 0.13) * 40, y: size.height * 0.10 + sin(t * 0.17) * 30),
                     radius: max(size.width, 320) * 0.85, color: Self.orange.opacity(0.30 * intensity))
                glow(&ctx, center: CGPoint(x: size.width * 0.05 + sin(t * 0.11) * 30, y: size.height * 0.92 + cos(t * 0.09) * 30),
                     radius: max(size.width, 320) * 0.75, color: Self.blue.opacity(0.18 * intensity))

                // two block chains moving in opposite directions
                chain(&ctx, size: size, y: size.height * 0.24, t: t, speed: 14, direction: -1)
                chain(&ctx, size: size, y: size.height * 0.78, t: t, speed: 10, direction: 1)

                // floating ₿ symbols
                for i in 0..<16 {
                    let seed = Double(i) + 1
                    let rx = fract(sin(seed * 12.9898) * 43758.5453)
                    let ry = fract(sin(seed * 78.233) * 12345.678)
                    let speed = 6 + 10 * fract(sin(seed * 3.7) * 999.1)
                    let fontSize = 14 + 26 * fract(sin(seed * 5.3) * 777.7)
                    let travel = size.height + 80
                    let y = size.height + 40 - (ry * travel + t * speed).truncatingRemainder(dividingBy: travel)
                    let x = rx * size.width + sin(t * 0.3 + seed) * 12
                    let opacity = (0.05 + 0.08 * fract(sin(seed * 9.1) * 555.5)) * intensity
                    var symbol = ctx
                    symbol.translateBy(x: x, y: y)
                    symbol.rotate(by: .degrees(sin(t * 0.2 + seed) * 12))
                    symbol.draw(Text("₿").font(.system(size: fontSize, weight: .heavy)).foregroundStyle(Self.orange.opacity(opacity)),
                                at: .zero)
                }
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }

    private func glow(_ ctx: inout GraphicsContext, center: CGPoint, radius: CGFloat, color: Color) {
        ctx.fill(Path(ellipseIn: CGRect(x: center.x - radius, y: center.y - radius, width: radius * 2, height: radius * 2)),
                 with: .radialGradient(Gradient(colors: [color, .clear]), center: center, startRadius: 0, endRadius: radius))
    }

    private func chain(_ ctx: inout GraphicsContext, size: CGSize, y: CGFloat, t: Double, speed: Double, direction: Double) {
        let w: CGFloat = 46, h: CGFloat = 32, gap: CGFloat = 30, step = w + gap
        let shift = CGFloat((t * speed).truncatingRemainder(dividingBy: Double(step))) * CGFloat(direction)
        var x = -step * 2 + shift
        let stroke = Self.orange.opacity(0.16 * intensity)
        while x < size.width + step {
            let block = Path(roundedRect: CGRect(x: x, y: y - h / 2, width: w, height: h), cornerRadius: 7)
            ctx.stroke(block, with: .color(stroke), lineWidth: 1.4)
            // little "transactions" inside each block
            for row in 0..<3 {
                let ly = y - h / 2 + 9 + CGFloat(row) * 7
                ctx.stroke(Path { p in p.move(to: CGPoint(x: x + 9, y: ly)); p.addLine(to: CGPoint(x: x + w - 9 - CGFloat(row * 6), y: ly)) },
                           with: .color(stroke.opacity(0.6)), lineWidth: 1)
            }
            ctx.stroke(Path { p in p.move(to: CGPoint(x: x + w, y: y)); p.addLine(to: CGPoint(x: x + step, y: y)) },
                       with: .color(stroke), style: StrokeStyle(lineWidth: 1.4, dash: [4, 3]))
            x += step
        }
    }

    private func fract(_ v: Double) -> Double { v - floor(v) }
}

/// Branded splash shown briefly at launch.
struct SplashView: View {
    @State private var appear = false

    var body: some View {
        ZStack {
            BTCBackground()
            VStack(spacing: 18) {
                Text("₿")
                    .font(.system(size: 64, weight: .heavy))
                    .foregroundStyle(Color(red: 0.10, green: 0.07, blue: 0.02))
                    .frame(width: 116, height: 116)
                    .background(LinearGradient(colors: [Color(red: 1, green: 0.71, blue: 0.29), Color(red: 0.85, green: 0.47, blue: 0.02)],
                                               startPoint: .topLeading, endPoint: .bottomTrailing),
                                in: RoundedRectangle(cornerRadius: 30, style: .continuous))
                    .shadow(color: Color.orange.opacity(0.45), radius: 30)
                    .scaleEffect(appear ? 1 : 0.8)
                VStack(spacing: 6) {
                    Text("Bitcoin Daily").font(.largeTitle.bold()).foregroundStyle(.white)
                    Text("Cycle · Flows · Mood").font(.subheadline.weight(.medium)).foregroundStyle(.white.opacity(0.6))
                }
                .opacity(appear ? 1 : 0)
            }
        }
        .onAppear { withAnimation(.spring(response: 0.6, dampingFraction: 0.7)) { appear = true } }
    }
}
