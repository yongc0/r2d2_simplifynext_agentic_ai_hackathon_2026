import { useState } from "react";
import { ArrowLeft, Camera, ShieldCheck } from "lucide-react";

import type { Intent, ProfileChip } from "../api/types";
import { intentLabel } from "../api/wire";

export interface ForeignerSignupResult {
  chips: ProfileChip[];
  profilePhoto: string | null;
}

export function ForeignerSignup({
  onBack,
  onComplete,
}: {
  onBack: () => void;
  onComplete: (result: ForeignerSignupResult) => void;
}) {
  const [photo, setPhoto] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(null);

  const readPhoto = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 4 * 1024 * 1024) {
      setPhotoError("Choose an image smaller than 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setPhoto(reader.result);
    };
    reader.readAsDataURL(file);
    setPhotoError(null);
  };

  const split = (data: FormData, name: string) =>
    String(data.get(name) ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 12);

  return (
    <form
      className="no-scrollbar h-full overflow-y-auto px-6 pt-10 pb-8"
      onSubmit={(event) => {
        event.preventDefault();
        const data = new FormData(event.currentTarget);
        const intent = String(data.get("intent") ?? "friends") as Intent;
        const chips: ProfileChip[] = [
          { kind: "intent", label: intentLabel(intent) },
          ...split(data, "characteristics").map((label) => ({ kind: "trait" as const, label })),
          ...split(data, "interests").map((label) => ({ kind: "interest" as const, label })),
          ...split(data, "values").map((label) => ({ kind: "value" as const, label })),
          ...split(data, "languages").map((label) => ({ kind: "language" as const, label })),
        ];
        onComplete({ chips, profilePhoto: photo });
        // The password field is deliberately never read into React/Zustand or
        // sent anywhere in this front-end prototype.
        event.currentTarget.reset();
      }}
    >
      <div className="mb-6 flex items-center justify-between">
        <button type="button" onClick={onBack} className="inline-flex items-center gap-1.5 text-xs font-semibold text-navy"><ArrowLeft size={15} /> Back</button>
        <span className="rounded-pill bg-peach/45 px-3 py-1.5 text-[10px] font-semibold tracking-wide text-navy">PROTOTYPE</span>
      </div>

      <h1 className="text-[1.75rem] leading-tight font-semibold tracking-tight text-text">Foreigner profile setup</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">Tell Spark what it needs for your account, matches and safety settings.</p>
      <p className="mt-3 rounded-card bg-peach/25 px-3 py-2 text-[10px] leading-relaxed text-navy ring-1 ring-clay/15 ring-inset">This demo does not create an account or retain credentials. Secure authentication and verification must be connected before launch.</p>

      <FormSection title="Account">
        <Field label="Email or phone number" name="contact" type="text" autoComplete="username" required />
        <Field label="Create password (not stored in demo)" name="password" type="password" autoComplete="new-password" minLength={8} required />
        <Field label="Date of birth" name="dateOfBirth" type="date" required />
        <Field label="Display name" name="displayName" type="text" maxLength={40} required />
      </FormSection>

      <FormSection title="Basic profile">
        <div className="flex items-center gap-3">
          {photo ? <img src={photo} alt="Profile preview" className="size-16 rounded-full object-cover" /> : <span className="grid size-16 shrink-0 place-items-center rounded-full bg-peach/40 text-navy"><Camera size={21} /></span>}
          <label className="cursor-pointer rounded-pill bg-navy px-4 py-2.5 text-xs font-semibold text-cream">Upload profile photo<input className="sr-only" type="file" accept="image/*" onChange={(event) => readPhoto(event.target.files?.[0])} /></label>
        </div>
        {photoError ? <p role="alert" className="text-xs text-clay">{photoError}</p> : null}
        <Field label="Name or nickname" name="nickname" type="text" maxLength={50} required />
        <Select label="Gender" name="gender" options={["Woman", "Man", "Non-binary", "Prefer to self-describe"]} />
        <Field label="Country and current location" name="location" type="text" maxLength={80} required />
      </FormSection>

      <FormSection title="About me">
        <TextArea label="Bio" name="bio" />
        <Field label="Occupation" name="occupation" type="text" />
        <Field label="Education" name="education" type="text" />
        <Field label="Languages (comma separated)" name="languages" type="text" required />
        <Field label="Interests and hobbies (comma separated)" name="interests" type="text" required />
      </FormSection>

      <FormSection title="Dating intent and match preferences">
        <label className="grid gap-1.5 text-xs font-medium text-navy">Dating intent<select name="intent" required className="rounded-xl border border-navy/15 bg-surface px-3 py-3 text-sm text-text focus:border-navy/40 focus:outline-none"><option value="partner_long_term">Long-term relationship</option><option value="partner_short_term">Short-term or casual dating</option><option value="friends">Friendship</option></select></label>
        <div className="grid grid-cols-2 gap-2"><Field label="Minimum age" name="minAge" type="number" min={18} max={99} /><Field label="Maximum age" name="maxAge" type="number" min={18} max={99} /></div>
        <Field label="Preferred distance (km)" name="distance" type="number" min={1} max={500} />
        <Field label="Genders to see" name="gendersToSee" type="text" />
        <Field label="Relationship goals" name="relationshipGoals" type="text" />
      </FormSection>

      <FormSection title="Lifestyle and personality">
        <Field label="Smoking, drinking and diet" name="lifestyle" type="text" />
        <Field label="Exercise, pets and sleep habits" name="habits" type="text" />
        <Field label="Characteristics (comma separated)" name="characteristics" type="text" required />
        <Field label="What matters to you (comma separated)" name="values" type="text" required />
        <TextArea label="A prompt or question others can answer" name="prompt" />
      </FormSection>

      <FormSection title="Safety and verification">
        <InfoRow icon={<ShieldCheck size={16} />} title="Social controls" detail="Likes, matches, messages, blocks and reports are managed after signup." />
        <InfoRow icon={<ShieldCheck size={16} />} title="Moderation history" detail="Reports and moderation events stay in a private safety record." />
        <label className="flex items-start gap-2 text-xs leading-relaxed text-muted"><input required type="checkbox" name="verificationConsent" className="mt-0.5 size-4 accent-navy" /> I agree to complete email/phone and selfie verification when secure services are connected.</label>
      </FormSection>

      <FormSection title="App settings">
        <Check label="Receive encounter and message notifications" name="notifications" defaultChecked />
        <Check label="Show me in discovery" name="discovery" defaultChecked />
        <Check label="Allow lock-ins to see my profile photo after reveal" name="photoVisibility" defaultChecked />
      </FormSection>

      <button type="submit" className="mt-2 w-full rounded-pill bg-navy px-6 py-4 text-sm font-semibold text-cream">Continue to profile questions</button>
    </form>
  );
}

function FormSection({ title, children }: { title: string; children: React.ReactNode }) {
  return <fieldset className="my-6 grid gap-3 rounded-card bg-cream/45 p-4 ring-1 ring-navy/10 ring-inset"><legend className="px-1 text-[10px] font-semibold tracking-[0.18em] text-navy/70 uppercase">{title}</legend>{children}</fieldset>;
}

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & { label: string; name: string };
function Field({ label, ...props }: FieldProps) {
  return <label className="grid gap-1.5 text-xs font-medium text-navy">{label}<input {...props} className="rounded-xl border border-navy/15 bg-surface px-3 py-3 text-sm text-text placeholder:text-muted focus:border-navy/40 focus:outline-none" /></label>;
}
function TextArea({ label, name }: { label: string; name: string }) {
  return <label className="grid gap-1.5 text-xs font-medium text-navy">{label}<textarea name={name} maxLength={300} rows={3} className="resize-none rounded-xl border border-navy/15 bg-surface px-3 py-3 text-sm text-text focus:border-navy/40 focus:outline-none" /></label>;
}
function Select({ label, name, options }: { label: string; name: string; options: string[] }) {
  return <label className="grid gap-1.5 text-xs font-medium text-navy">{label}<select name={name} className="rounded-xl border border-navy/15 bg-surface px-3 py-3 text-sm text-text">{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}
function Check({ label, name, defaultChecked }: { label: string; name: string; defaultChecked?: boolean }) {
  return <label className="flex items-center gap-2 text-xs text-text"><input type="checkbox" name={name} defaultChecked={defaultChecked} className="size-4 accent-navy" /> {label}</label>;
}
function InfoRow({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) {
  return <div className="flex gap-2.5 text-navy">{icon}<div><p className="text-xs font-semibold">{title}</p><p className="mt-0.5 text-[11px] leading-relaxed text-muted">{detail}</p></div></div>;
}
