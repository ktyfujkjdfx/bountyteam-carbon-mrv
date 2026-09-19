/**
 * Тонкие линейные иконки, нарисованные здесь же. Внешних наборов нет намеренно: офлайн-сборка
 * не должна тянуть шрифт иконок или спрайт со стороннего хоста.
 */
interface IconProps {
  size?: number;
}

function svg(size: number, children: React.ReactNode) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function LeafIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M5 19c0-7 5-12 14-13 1 9-4 14-11 14H5z" />
    <path d="M5 19c3-4 6-6 10-7" />
  </>);
}

export function CloudIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M7 18h10a3.5 3.5 0 0 0 .3-7A5 5 0 0 0 8 9.5 3.75 3.75 0 0 0 7 18z" />
  </>);
}

export function TrendIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M4 16l5-5 3 3 6-7" />
    <path d="M14 7h4v4" />
  </>);
}

export function CoinsIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <ellipse cx="12" cy="6.5" rx="7" ry="2.8" />
    <path d="M5 6.5v5c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8v-5" />
    <path d="M5 11.5v5c0 1.6 3.1 2.8 7 2.8s7-1.2 7-2.8v-5" />
  </>);
}

export function CheckIcon({ size = 18 }: IconProps) {
  return svg(size, <path d="M5 12.5l4.5 4.5L19 7.5" />);
}

export function MinusIcon({ size = 18 }: IconProps) {
  return svg(size, <path d="M6 12h12" />);
}

export function ShieldIcon({ size = 18 }: IconProps) {
  return svg(size, <path d="M12 3.5l7 2.5v5c0 4-3 7.2-7 9.5-4-2.3-7-5.5-7-9.5v-5l7-2.5z" />);
}

export function DocIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M6.5 3.5h7l4.5 4.5v12h-11.5z" />
    <path d="M13.5 3.5V8H18" />
    <path d="M9 12.5h6M9 16h4" />
  </>);
}

export function LayersIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M12 4l8 4-8 4-8-4 8-4z" />
    <path d="M4 12l8 4 8-4" />
    <path d="M4 16l8 4 8-4" />
  </>);
}

export function ImageIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <rect x="4" y="5" width="16" height="14" rx="2" />
    <circle cx="9" cy="10" r="1.6" />
    <path d="M5 17l4.5-4.5 3.5 3.5 2.5-2.5L19 16" />
  </>);
}

export function TreeIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M12 3.5l4.5 6h-9z" />
    <path d="M12 8l5.5 7h-11z" />
    <path d="M12 15v5.5" />
  </>);
}

export function ListIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M9 7h11M9 12h11M9 17h7" />
    <path d="M4.5 7h.01M4.5 12h.01M4.5 17h.01" />
  </>);
}

export function AlertIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M12 4.5l8.5 15h-17z" />
    <path d="M12 10v4.5M12 17.2h.01" />
  </>);
}

export function ArrowIcon({ size = 18 }: IconProps) {
  return svg(size, <>
    <path d="M5 12h13" />
    <path d="M13.5 7l5 5-5 5" />
  </>);
}
