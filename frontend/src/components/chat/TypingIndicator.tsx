/** Three pulsing dots shown between sending a message and the first token. */
export default function TypingIndicator() {
  return (
    <span
      className="inline-flex items-center gap-1 py-1"
      role="status"
      aria-label="Applify is typing"
    >
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-text-faint"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </span>
  )
}
