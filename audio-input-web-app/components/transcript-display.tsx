"use client"

interface TranscriptDisplayProps {
  transcript: string
  label?: string
}

export default function TranscriptDisplay({ transcript, label = "Response" }: TranscriptDisplayProps) {
  return (
    <div className="w-full p-6 bg-card border border-border rounded-lg">
      <h2 className="text-lg font-semibold mb-3 text-foreground">{label}</h2>
      <p className="text-foreground leading-relaxed break-words">{transcript}</p>
    </div>
  )
}
