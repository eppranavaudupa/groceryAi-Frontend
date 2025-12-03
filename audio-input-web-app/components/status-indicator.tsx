"use client"

interface StatusIndicatorProps {
  status: string
}

export default function StatusIndicator({ status }: StatusIndicatorProps) {
  const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
    ready: { bg: "bg-blue-50", text: "text-blue-900", dot: "bg-blue-500" },
    recording: { bg: "bg-red-50", text: "text-red-900", dot: "bg-red-500" },
    processing: { bg: "bg-yellow-50", text: "text-yellow-900", dot: "bg-yellow-500" },
    done: { bg: "bg-green-50", text: "text-green-900", dot: "bg-green-500" },
    error: { bg: "bg-destructive/10", text: "text-destructive", dot: "bg-destructive" },
  }

  const current = statusColors[status] || statusColors.ready

  return (
    <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${current.bg}`}>
      <div className={`w-3 h-3 rounded-full ${current.dot} animate-pulse`}></div>
      <span className={`font-semibold ${current.text}`}>{status.toUpperCase()}</span>
    </div>
  )
}
