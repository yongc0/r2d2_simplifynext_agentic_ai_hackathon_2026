import { useRef, useState } from "react";
import { ArrowLeft, FileText, Image, Mic, Send } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { NAV_HEIGHT_CLASS } from "../components/AppNav";
import type { ChatAttachment } from "../store/useSpark";
import { useSpark } from "../store/useSpark";

const CENSORED = ["fuck", "shit", "bitch", "idiot", "kill", "hate"];
const MAX_FILE_BYTES = 8 * 1024 * 1024;

export function moderateMessage(value: string): { text: string; moderated: boolean } {
  let moderated = false;
  let text = value;
  for (const word of CENSORED) {
    const expression = new RegExp(`\\b${word}\\b`, "gi");
    if (expression.test(text)) {
      moderated = true;
      text = text.replace(expression, "•".repeat(word.length));
    }
  }
  return { text, moderated };
}

export default function Chat() {
  const { lockInId = "" } = useParams();
  const navigate = useNavigate();
  const lockIn = useSpark((state) => state.lockIns.find((item) => item.lockInId === lockInId));
  const messages = useSpark((state) => state.chats[lockInId] ?? []);
  const sendMessage = useSpark((state) => state.sendChatMessage);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const photoInput = useRef<HTMLInputElement>(null);
  const voiceInput = useRef<HTMLInputElement>(null);
  const documentInput = useRef<HTMLInputElement>(null);

  if (!lockIn || lockIn.state === "released") {
    return (
      <div className="grid h-full place-items-center px-8 text-center">
        <div>
          <p className="text-sm text-muted">Chat is available only for an active lock-in.</p>
          <button type="button" onClick={() => navigate("/lockins")} className="mt-4 rounded-pill bg-navy px-5 py-3 text-sm text-cream">Back to lock-ins</button>
        </div>
      </div>
    );
  }

  const submitText = () => {
    const clean = draft.trim();
    if (!clean) return;
    const result = moderateMessage(clean);
    sendMessage(lockInId, { from: "you", text: result.text, moderated: result.moderated });
    setDraft("");
  };

  const attach = (file: File | undefined, kind: ChatAttachment["kind"]) => {
    if (!file) return;
    if (file.size > MAX_FILE_BYTES) {
      setError("Attachments must be smaller than 8 MB.");
      return;
    }
    const allowed = kind === "photo" ? file.type.startsWith("image/") : kind === "voice" ? file.type.startsWith("audio/") : true;
    if (!allowed) {
      setError(`Choose a valid ${kind} file.`);
      return;
    }
    setError(null);
    const finish = (dataUrl?: string) => sendMessage(lockInId, {
      from: "you",
      text: "",
      attachment: { kind, name: file.name, mimeType: file.type || "application/octet-stream", dataUrl },
    });
    if (kind === "document") return finish();
    const reader = new FileReader();
    reader.onload = () => finish(typeof reader.result === "string" ? reader.result : undefined);
    reader.readAsDataURL(file);
  };

  return (
    <div className={`flex h-full flex-col ${NAV_HEIGHT_CLASS}`}>
      <header className="flex items-center gap-3 border-b border-navy/10 px-5 pb-4">
        <button type="button" onClick={() => navigate("/lockins")} aria-label="Back to lock-ins" className="grid size-9 place-items-center rounded-full bg-cream text-navy"><ArrowLeft size={18} /></button>
        <div>
          <h1 className="text-base font-semibold text-text">{lockIn.person.displayName}</h1>
          <p className="text-[10px] font-medium text-emerald-700">LOCK-IN CHAT</p>
        </div>
      </header>

      <div className="no-scrollbar flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        <p className="rounded-card bg-peach/25 px-3 py-2 text-center text-[10px] leading-relaxed text-navy">
          Harmful language is automatically masked. Report anything that still feels unsafe.
        </p>
        {messages.length === 0 ? <p className="my-auto text-center text-sm text-muted">Start a conversation with {lockIn.person.displayName}.</p> : null}
        {messages.map((message) => (
          <div key={message.messageId} className={`flex ${message.from === "you" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-card px-3.5 py-2.5 text-sm ${message.from === "you" ? "bg-navy text-cream" : "bg-surface text-text ring-1 ring-navy/10 ring-inset"}`}>
              {message.attachment?.kind === "photo" && message.attachment.dataUrl ? <img src={message.attachment.dataUrl} alt={message.attachment.name} className="mb-1 max-h-48 rounded-xl object-cover" /> : null}
              {message.attachment?.kind === "voice" && message.attachment.dataUrl ? <audio controls src={message.attachment.dataUrl} className="max-w-full" aria-label={message.attachment.name} /> : null}
              {message.attachment?.kind === "document" ? <span className="inline-flex items-center gap-2"><FileText size={15} /> {message.attachment.name}</span> : null}
              {message.text ? <p>{message.text}</p> : null}
              {message.moderated ? <p className="mt-1 text-[9px] opacity-70">Some language was masked</p> : null}
            </div>
          </div>
        ))}
      </div>

      <div className="border-t border-navy/10 bg-surface px-4 pt-3 pb-4">
        {error ? <p role="alert" className="mb-2 text-xs text-clay">{error}</p> : null}
        <div className="mb-2 flex gap-2">
          <AttachmentButton label="Photo" Icon={Image} onClick={() => photoInput.current?.click()} />
          <AttachmentButton label="Voice" Icon={Mic} onClick={() => voiceInput.current?.click()} />
          <AttachmentButton label="Document" Icon={FileText} onClick={() => documentInput.current?.click()} />
          <input ref={photoInput} className="hidden" type="file" accept="image/*" onChange={(event) => attach(event.target.files?.[0], "photo")} />
          <input ref={voiceInput} className="hidden" type="file" accept="audio/*" capture onChange={(event) => attach(event.target.files?.[0], "voice")} />
          <input ref={documentInput} className="hidden" type="file" accept=".pdf,.doc,.docx,.txt" onChange={(event) => attach(event.target.files?.[0], "document")} />
        </div>
        <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); submitText(); }}>
          <input value={draft} onChange={(event) => setDraft(event.target.value)} aria-label="Message" placeholder="Message privately" className="min-w-0 flex-1 rounded-pill border border-navy/15 bg-cream/55 px-4 py-3 text-sm text-text placeholder:text-muted focus:border-navy/40 focus:outline-none" />
          <button type="submit" disabled={!draft.trim()} aria-label="Send message" className="grid size-11 place-items-center rounded-full bg-navy text-cream disabled:opacity-35"><Send size={17} /></button>
        </form>
      </div>
    </div>
  );
}

function AttachmentButton({ label, Icon, onClick }: { label: string; Icon: typeof Image; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="inline-flex items-center gap-1.5 rounded-pill bg-cream px-3 py-2 text-[11px] font-medium text-navy ring-1 ring-navy/10 ring-inset"><Icon size={14} /> {label}</button>;
}
