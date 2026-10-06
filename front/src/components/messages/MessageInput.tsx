import { MAX_MESSAGE_LENGTH } from "@/lib/limits";
import { Button } from "@/components/ui/Button";

export interface MessageInputProps {
  value: string;
  onChange: (value: string) => void;
  onTyping?: () => void;
  onSubmit: (e: React.FormEvent) => void;
  placeholder?: string;
  disabled?: boolean;
  cooldown?: number;
}

export function MessageInput({
  value,
  onChange,
  onTyping,
  onSubmit,
  placeholder = "Écrivez votre message...",
  disabled = false,
  cooldown,
}: MessageInputProps) {
  const isCooldown = cooldown != null && cooldown > 0;

  return (
    <form
      onSubmit={onSubmit}
      className="p-2.5 sm:p-3 border-t border-gray-200 bg-white flex items-center gap-2 shrink-0"
    >
      <input
        type="text"
        placeholder={isCooldown ? `Patientez ${cooldown}s...` : placeholder}
        value={value}
        maxLength={MAX_MESSAGE_LENGTH}
        onChange={(e) => {
          onChange(e.target.value);
          onTyping?.();
        }}
        className="flex-1 p-2.5 border border-gray-300 rounded-lg text-base sm:text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
      />
      <Button type="submit" disabled={disabled || isCooldown || !value.trim()} className="shrink-0">
        {isCooldown ? `Patientez (${cooldown}s)` : "Envoyer"}
      </Button>
    </form>
  );
}
