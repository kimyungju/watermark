import { useState, useRef, useCallback } from "react";

const ACCEPTED_TYPES = [".png", ".jpg", ".jpeg", ".pdf"];
const MAX_SIZE = 10 * 1024 * 1024;
const MAX_FILES = 5;

function validateFiles(fileList) {
  const valid = [];
  const errors = [];

  for (const file of fileList) {
    const ext = "." + file.name.split(".").pop().toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      errors.push(`${file.name}: unsupported file type`);
    } else if (file.size > MAX_SIZE) {
      errors.push(`${file.name}: exceeds 10 MB limit`);
    } else {
      valid.push(file);
    }
  }

  if (valid.length > MAX_FILES) {
    errors.push(`Too many files. Maximum is ${MAX_FILES}.`);
    return { valid: valid.slice(0, MAX_FILES), errors };
  }

  return { valid, errors };
}

export default function UploadZone({ onUpload, disabled }) {
  const [dragOver, setDragOver] = useState(false);
  const [clientErrors, setClientErrors] = useState([]);
  const inputRef = useRef(null);

  const handleFiles = useCallback(
    (fileList) => {
      setClientErrors([]);
      const { valid, errors } = validateFiles(Array.from(fileList));
      if (errors.length > 0) {
        setClientErrors(errors);
      }
      if (valid.length > 0) {
        onUpload(valid);
      }
    },
    [onUpload]
  );

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDragOver(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles]
  );

  return (
    <div className="mt-8">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`group relative cursor-pointer rounded-2xl p-10 text-center transition-all duration-300 ${
          disabled ? "pointer-events-none opacity-50" : ""
        }`}
        style={{
          background: dragOver
            ? "linear-gradient(135deg, var(--color-accent-glow), transparent)"
            : "var(--color-surface)",
          border: `1px solid ${dragOver ? "var(--color-accent)" : "var(--color-border)"}`,
        }}
      >
        {/* Hover glow */}
        <div
          className="pointer-events-none absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--color-accent-glow) 0%, transparent 70%)",
          }}
        />

        <div className="relative">
          {/* Upload icon */}
          <div
            className={`mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-xl transition-all duration-300 ${
              dragOver
                ? "bg-[var(--color-accent)] text-[var(--color-base)] scale-110"
                : "bg-[var(--color-surface-raised)] text-[var(--color-text-muted)] group-hover:text-[var(--color-accent)]"
            }`}
          >
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>

          <p
            className={`text-base font-medium transition-colors duration-300 ${
              dragOver
                ? "text-[var(--color-accent)]"
                : "text-[var(--color-text)]"
            }`}
          >
            {dragOver ? "Drop to upload" : "Drop files here or click to browse"}
          </p>
          <p className="mt-2 text-sm text-[var(--color-text-dim)]">
            PNG, JPG, PDF &mdash; up to 10 MB each, 5 files max
          </p>
        </div>

        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".png,.jpg,.jpeg,.pdf"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {clientErrors.length > 0 && (
        <div className="animate-fade-up mt-4 rounded-xl border border-[var(--color-error)]/20 bg-[var(--color-error)]/5 px-4 py-3 text-sm text-[var(--color-error)]">
          {clientErrors.map((err, i) => (
            <p key={i}>{err}</p>
          ))}
        </div>
      )}
    </div>
  );
}
