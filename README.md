IN FRONTEND IN APP FOLDER 
"use client"

import { useEffect, useRef, useState } from "react"
import AudioButton from "@/components/audio-button"
import TranscriptDisplay from "@/components/transcript-display"
import StatusIndicator from "@/components/status-indicator"

export default function Home(): JSX.Element {
  const [transcript, setTranscript] = useState<string>("")
  const [apiResponse, setApiResponse] = useState<string>("")
  const [isRecording, setIsRecording] = useState<boolean>(false)
  const [status, setStatus] = useState<"ready" | "recording" | "processing" | "done" | "error">("ready")
  const [error, setError] = useState<string>("")
  const [cartItems, setCartItems] = useState<any[]>([])

  const recognitionRef = useRef<any>(null)
  const synthRef = useRef<SpeechSynthesis | null>(null)

  const getApiBase = () => {
    if (typeof window === "undefined") return "http://localhost:5000"
    const host = window.location.hostname
    return `http://${host}:5000`
  }

  useEffect(() => {
    if (typeof window === "undefined") return

    synthRef.current = window.speechSynthesis ?? null

    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition

    if (!SpeechRecognition) {
      setStatus("error")
      setError("Speech Recognition is not supported in this browser")
      return
    }

    const recognition = new SpeechRecognition()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = "en-US"

    recognition.onresult = (event: any) => {
      let finalTranscript = ""
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript
        }
      }
      if (finalTranscript) {
        setTranscript(finalTranscript)
        announceToScreenReader(`Heard: ${finalTranscript}`)
        sendToAPI(finalTranscript)
      }
    }

    recognition.onerror = (event: any) => {
      setStatus("error")
      setError(`Speech recognition error: ${event?.error ?? event}`)
      announceToScreenReader(`Error: ${event?.error ?? event}`)
    }

    recognitionRef.current = recognition

    // fetch cart on mount
    fetchCart()

    return () => {
      try { recognition.stop?.() } catch (err) {}
      try { synthRef.current?.cancel() } catch (err) {}
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startRecording = () => {
    if (!recognitionRef.current) {
      setStatus("error")
      setError("SpeechRecognition unavailable")
      return
    }

    try {
      setIsRecording(true)
      setStatus("recording")
      setError("")
      setTranscript("")
      setApiResponse("")
      recognitionRef.current.start()
      announceToScreenReader("Recording started. Speak now.")
    } catch (err: any) {
      setStatus("error")
      setError(`Failed to start recording: ${err?.message ?? String(err)}`)
    }
  }

  const stopRecording = () => {
    if (!recognitionRef.current) return
    try {
      recognitionRef.current.stop()
      setIsRecording(false)
    } catch (err: any) {
      setStatus("error")
      setError(`Failed to stop recording: ${err?.message ?? String(err)}`)
    }
  }

  const sendToAPI = async (prompt: string) => {
    setStatus("processing")
    announceToScreenReader("Sending to server...")

    const apiBase = getApiBase()
    const url = `${apiBase}/ai`

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ user_prompt: prompt }),
      })

      if (!response.ok) {
        const text = await response.text().catch(() => "")
        throw new Error(`API request failed: ${response.status} ${text}`)
      }

      const data = await response.json()
      console.log("[v0] API Response:", data)

      const responseText = data.response || data.text || JSON.stringify(data)
      setApiResponse(responseText)
      setStatus("done")
      announceToScreenReader("Got response. Converting to speech.")

      // fetch cart (in case it changed) and speak
      await fetchCart()
      speakResponse(responseText)
    } catch (err: any) {
      setStatus("error")
      setError(
        `Failed to get response: ${err?.message ?? String(err)}. Make sure the API server is running and accessible from this device.`
      )
      announceToScreenReader(`Error: ${err?.message ?? String(err)}`)
      console.error("sendToAPI error:", err)
    }
  }

  const fetchCart = async () => {
    const apiBase = getApiBase()
    try {
      const res = await fetch(`${apiBase}/cart`, { credentials: "include" })
      if (!res.ok) {
        console.warn("Failed to fetch cart:", res.status)
        return
      }
      const payload = await res.json()
      const cart = payload?.cart ?? payload
      setCartItems(cart?.items ?? [])
    } catch (err) {
      console.error("Error fetching cart:", err)
    }
  }

  const downloadPDF = async () => {
    const apiBase = getApiBase()
    try {
      const res = await fetch(`${apiBase}/download-pdf`, { credentials: "include" })
      if (!res.ok) {
        const t = await res.text().catch(() => "")
        // show server error text to help debugging
        throw new Error(`download failed: ${res.status} ${t}`)
      }
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "grocery-cart.pdf"
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err: any) {
      console.error("Error downloading PDF:", err)
      setError(String(err?.message ?? err))
    }
  }

  // === New functions: clearCart and resetSession ===
  const clearCart = async () => {
    const apiBase = getApiBase()
    try {
      const res = await fetch(`${apiBase}/cart/clear`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
      if (!res.ok) {
        const t = await res.text().catch(() => "")
        throw new Error(`clear cart failed: ${res.status} ${t}`)
      }
      await fetchCart()
      setApiResponse("Cart cleared.")
      announceToScreenReader("Cart cleared.")
    } catch (err: any) {
      console.error("clearCart error:", err)
      setError(String(err?.message ?? err))
    }
  }

  const resetSession = async () => {
    const apiBase = getApiBase()
    try {
      const res = await fetch(`${apiBase}/session/reset`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
      })
      if (!res.ok) {
        const t = await res.text().catch(() => "")
        throw new Error(`reset session failed: ${res.status} ${t}`)
      }
      // new session created on server (new session_id), refresh client state
      setTranscript("")
      setApiResponse("")
      setCartItems([])
      setStatus("ready")
      setError("")
      announceToScreenReader("Session reset. Fresh cart ready.")
    } catch (err: any) {
      console.error("resetSession error:", err)
      setError(String(err?.message ?? err))
    }
  }
  // === end new functions ===

  const speakResponse = (text: string) => {
    if (typeof window === "undefined" || !synthRef.current) {
      console.warn("SpeechSynthesis not available")
      return
    }

    try {
      synthRef.current.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.rate = 1
      utterance.pitch = 1
      utterance.volume = 1

      utterance.onstart = () => announceToScreenReader("Speaking response...")
      utterance.onend = () => {
        announceToScreenReader("Done. Ready for next input.")
        setStatus("ready")
      }
      utterance.onerror = (event: any) => {
        setStatus("error")
        setError(`Speech synthesis error: ${event?.error ?? event}`)
        announceToScreenReader(`Error: ${event?.error ?? event}`)
      }

      synthRef.current.speak(utterance)
    } catch (err: any) {
      setStatus("error")
      setError(`SpeechSynthesis failed: ${err?.message ?? String(err)}`)
    }
  }

  const announceToScreenReader = (message: string) => {
    if (typeof document === "undefined") return
    const announcement = document.createElement("div")
    announcement.setAttribute("role", "status")
    announcement.setAttribute("aria-live", "polite")
    announcement.setAttribute("aria-atomic", "true")
    announcement.textContent = message
    announcement.className = "sr-only"
    document.body.appendChild(announcement)
    setTimeout(() => {
      try { document.body.removeChild(announcement) } catch (err) {}
    }, 1000)
  }

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter" && !isRecording) {
        e.preventDefault()
        startRecording()
      }
    }
    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Enter" && isRecording) {
        e.preventDefault()
        stopRecording()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    window.addEventListener("keyup", handleKeyUp)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      window.removeEventListener("keyup", handleKeyUp)
    }
  }, [isRecording])

  return (
    <main className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="flex flex-col items-center justify-center gap-8 w-full max-w-md">
        <StatusIndicator status={status} />

        <h1 className="sr-only">Audio Input Assistant</h1>
        <p className="text-center text-muted-foreground text-lg">
          Press and hold <kbd className="font-semibold text-foreground">Enter</kbd> to record
        </p>

        <AudioButton isRecording={isRecording} onClick={isRecording ? stopRecording : startRecording} />

        {transcript && <TranscriptDisplay transcript={transcript} label="You said:" />}
        {apiResponse && <TranscriptDisplay transcript={apiResponse} label="Response:" />}

        <div className="cart-section w-full border rounded-lg p-4 bg-card">
          <h3 className="text-lg font-semibold mb-3">Shopping Cart ({cartItems.length} items)</h3>
          {cartItems.length === 0 ? (
            <p className="text-muted-foreground text-center">Your cart is empty</p>
          ) : (
            <ul className="space-y-2 mb-4">
              {cartItems.map((it, idx) => (
                <li key={idx} className="flex justify-between items-center border-b pb-2">
                  <span className="font-medium">{it.item}</span>
                  <span className="text-muted-foreground">
                    ₹{it.price} × {it.quantity} = ₹{(it.total ?? (it.price * it.quantity)).toFixed(2)}
                  </span>
                </li>
              ))}
              <li className="flex justify-between items-center pt-2 font-bold border-t">
                <span>Total:</span>
                <span>
                  ₹{cartItems.reduce((s, it) => s + (it.total ?? (it.price * it.quantity)), 0).toFixed(2)}
                </span>
              </li>
            </ul>
          )}

          {/* Buttons: Download, Clear Cart, Reset Session */}
          <div className="flex gap-2 mt-3">
            <button
              onClick={downloadPDF}
              className="flex-1 py-2 px-4 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
              disabled={cartItems.length === 0}
            >
              Download Cart as PDF
            </button>

            <button
              onClick={clearCart}
              className="py-2 px-4 bg-yellow-600 text-white rounded-lg hover:opacity-95 transition-colors"
              disabled={cartItems.length === 0}
              title="Empty only the cart items (keeps session)"
            >
              Clear Cart
            </button>

            <button
              onClick={resetSession}
              className="py-2 px-4 bg-red-600 text-white rounded-lg hover:opacity-95 transition-colors"
              title="Reset whole session (new session id)"
            >
              Reset Session
            </button>
          </div>
        </div>

        {error && (
          <div className="p-4 bg-destructive/10 border border-destructive text-destructive rounded-lg w-full text-center" role="alert">
            {error}
          </div>
        )}

        <p className="text-center text-sm text-muted-foreground">
          {status === "ready" && "Ready to record. Press and hold Enter or click the button."}
          {status === "recording" && "Recording... Release to stop."}
          {status === "processing" && "Processing your request..."}
          {status === "done" && "Done! Listen to the response or press Enter again."}
          {status === "error" && "An error occurred. Please try again."}
        </p>
      </div>
    </main>
  )
}
 page.tsx
 import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { Analytics } from '@vercel/analytics/next'
import './globals.css'

const _geist = Geist({ subsets: ["latin"] });
const _geistMono = Geist_Mono({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: 'v0 App',
  description: 'Created with v0',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className={`font-sans antialiased`}>
        {children}
        <Analytics />
      </body>
    </html>
  )
}
layout.tsx
@import 'tailwindcss';
@import 'tw-animate-css';

@custom-variant dark (&:is(.dark *));

:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.577 0.245 27.325);
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);
  --chart-1: oklch(0.646 0.222 41.116);
  --chart-2: oklch(0.6 0.118 184.704);
  --chart-3: oklch(0.398 0.07 227.392);
  --chart-4: oklch(0.828 0.189 84.429);
  --chart-5: oklch(0.769 0.188 70.08);
  --radius: 0.625rem;
  --sidebar: oklch(0.985 0 0);
  --sidebar-foreground: oklch(0.145 0 0);
  --sidebar-primary: oklch(0.205 0 0);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.97 0 0);
  --sidebar-accent-foreground: oklch(0.205 0 0);
  --sidebar-border: oklch(0.922 0 0);
  --sidebar-ring: oklch(0.708 0 0);
}

.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --card: oklch(0.145 0 0);
  --card-foreground: oklch(0.985 0 0);
  --popover: oklch(0.145 0 0);
  --popover-foreground: oklch(0.985 0 0);
  --primary: oklch(0.985 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
  --secondary-foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --accent: oklch(0.269 0 0);
  --accent-foreground: oklch(0.985 0 0);
  --destructive: oklch(0.396 0.141 25.723);
  --destructive-foreground: oklch(0.637 0.237 25.331);
  --border: oklch(0.269 0 0);
  --input: oklch(0.269 0 0);
  --ring: oklch(0.439 0 0);
  --chart-1: oklch(0.488 0.243 264.376);
  --chart-2: oklch(0.696 0.17 162.48);
  --chart-3: oklch(0.769 0.188 70.08);
  --chart-4: oklch(0.627 0.265 303.9);
  --chart-5: oklch(0.645 0.246 16.439);
  --sidebar: oklch(0.205 0 0);
  --sidebar-foreground: oklch(0.985 0 0);
  --sidebar-primary: oklch(0.488 0.243 264.376);
  --sidebar-primary-foreground: oklch(0.985 0 0);
  --sidebar-accent: oklch(0.269 0 0);
  --sidebar-accent-foreground: oklch(0.985 0 0);
  --sidebar-border: oklch(0.269 0 0);
  --sidebar-ring: oklch(0.439 0 0);
}

@theme inline {
  --font-sans: 'Geist', 'Geist Fallback';
  --font-mono: 'Geist Mono', 'Geist Mono Fallback';
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground;
  }
}
global.css
