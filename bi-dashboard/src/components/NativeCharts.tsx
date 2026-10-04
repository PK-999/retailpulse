import { useEffect, useMemo, useRef, useState } from "react";

interface LinePoint {
  label: string;
  value: number;
}

interface LineChartProps {
  points: LinePoint[];
  label: string;
  color: string;
  gradientId: string;
  formatValue: (value: number) => string;
}

const width = 820;
const height = 310;
const padding = { top: 18, right: 18, bottom: 42, left: 68 };

function tickIndexes(length: number, count = 5): number[] {
  if (length <= 1) return [0];
  return Array.from(
    new Set(
      Array.from({ length: Math.min(count, length) }, (_, index) =>
        Math.round((index * (length - 1)) / (Math.min(count, length) - 1)),
      ),
    ),
  );
}

export function NativeLineChart({
  points,
  label,
  color,
  gradientId,
  formatValue,
}: LineChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(width);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setChartWidth(Math.max(300, Math.round(entry.contentRect.width)));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const geometry = useMemo(() => {
    const max = Math.max(...points.map((point) => point.value), 1);
    const plotWidth = chartWidth - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const coordinates = points.map((point, index) => ({
      ...point,
      x: padding.left + (index / Math.max(points.length - 1, 1)) * plotWidth,
      y: padding.top + plotHeight - (point.value / max) * plotHeight,
    }));
    const line = coordinates
      .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)},${point.y.toFixed(2)}`)
      .join(" ");
    const area = coordinates.length
      ? `${line} L${coordinates.at(-1)!.x},${padding.top + plotHeight} L${coordinates[0].x},${padding.top + plotHeight} Z`
      : "";
    return { area, coordinates, line, max, plotHeight };
  }, [points, chartWidth]);

  if (!points.length) {
    return <div className="native-empty">No observations in this snapshot.</div>;
  }

  return (
    <div className="native-chart" role="img" aria-label={label} ref={container}>
      <svg viewBox={`0 0 ${chartWidth} ${height}`} preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.3" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding.top + geometry.plotHeight * ratio;
          const value = geometry.max * (1 - ratio);
          return (
            <g key={ratio}>
              <line x1={padding.left} y1={y} x2={chartWidth - padding.right} y2={y} className="chart-gridline" />
              <text x={padding.left - 10} y={y + 4} textAnchor="end" className="chart-axis-label">
                {formatValue(value)}
              </text>
            </g>
          );
        })}

        <path d={geometry.area} fill={`url(#${gradientId})`} />
        <path d={geometry.line} fill="none" stroke={color} strokeWidth="3" vectorEffect="non-scaling-stroke" />

        {tickIndexes(points.length, chartWidth < 500 ? 3 : 5).map((index) => {
          const point = geometry.coordinates[index];
          return (
            <g key={`${point.label}-${index}`}>
              <circle cx={point.x} cy={point.y} r="4" fill={color} stroke="#07111f" strokeWidth="2" vectorEffect="non-scaling-stroke" />
              <text x={point.x} y={height - 12} textAnchor="middle" className="chart-axis-label">
                {point.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

interface CountryBar {
  country: string;
  revenue: number;
}

export function CountryBars({ rows, formatValue }: {
  rows: CountryBar[];
  formatValue: (value: number) => string;
}) {
  if (!rows.length) return <div className="native-empty">No observations in this snapshot.</div>;
  const max = Math.max(...rows.map((row) => row.revenue), 1);
  return (
    <div className="country-bars" role="img" aria-label="Revenue by country">
      {rows.slice(0, 7).map((row) => (
        <div className="country-bar-row" key={row.country}>
          <div><strong>{row.country}</strong><span>{formatValue(row.revenue)}</span></div>
          <div className="country-track">
            <span style={{ width: `${Math.max(3, (row.revenue / max) * 100)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function InventoryDonut({ healthy, stale, unknown }: {
  healthy: number;
  stale: number;
  unknown: number;
}) {
  const total = healthy + stale + unknown;
  const healthyEnd = total ? (healthy / total) * 100 : 0;
  const staleEnd = total ? healthyEnd + (stale / total) * 100 : 0;
  const background = `conic-gradient(
    var(--green) 0% ${healthyEnd}%,
    var(--amber) ${healthyEnd}% ${staleEnd}%,
    #52657b ${staleEnd}% 100%
  )`;

  return (
    <div className="donut-wrap" role="img" aria-label={`${healthy} healthy, ${stale} stale and ${unknown} unknown inventory records`}>
      <div className="donut" style={{ background }}>
        <div><strong>{total}</strong><span>products</span></div>
      </div>
      <div className="donut-legend">
        <span><i className="healthy" />Healthy <strong>{healthy}</strong></span>
        <span><i className="stale" />Stale <strong>{stale}</strong></span>
        <span><i className="unknown" />Unknown <strong>{unknown}</strong></span>
      </div>
    </div>
  );
}
