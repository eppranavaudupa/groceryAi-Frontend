"use client"

interface AudioButtonProps {
  isRecording: boolean
  onClick: () => void
}

export default function AudioButton({ isRecording, onClick }: AudioButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`
        w-40 h-40 rounded-full flex items-center justify-center
        text-white text-2xl font-bold transition-all duration-200
        border-4 focus:outline-none focus:ring-4 focus:ring-offset-4
        ${
          isRecording
            ? "bg-destructive hover:bg-destructive/90 border-destructive focus:ring-destructive/50"
            : "bg-primary hover:bg-primary/90 border-primary focus:ring-primary/50"
        }
        shadow-lg hover:shadow-xl active:shadow-md
        touch-none cursor-pointer
      `}
      aria-pressed={isRecording}
      aria-label={isRecording ? "Stop recording" : "Start recording"}
      title={isRecording ? "Stop recording (hold Enter)" : "Start recording (hold Enter)"}
    >
      <div className="flex flex-col items-center gap-2">
        {isRecording ? (
          <>
            <div className="animate-pulse">🔴</div>
            <span className="text-sm">STOP</span>
          </>
        ) : (
          <>
            <div>🎤</div>
            <span className="text-sm">START</span>
          </>
        )}
      </div>
    </button>
  )
}
