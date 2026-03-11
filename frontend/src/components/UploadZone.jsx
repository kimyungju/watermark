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
    <div className="mt-10">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-colors ${
          dragOver
            ? "border-blue-400 bg-blue-400/10"
            : "border-gray-700 hover:border-gray-500"
        } ${disabled ? "pointer-events-none opacity-50" : ""}`}
      >
        <div className="text-4xl">{"\u{1F4C1}"}</div>
        <p className="mt-3 text-gray-300">Drop files here or click to upload</p>
        <p className="mt-1 text-sm text-gray-500">
          PNG, JPG, PDF — max 10 MB, up to 5 files
        </p>
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
        <div className="mt-4 rounded-lg bg-red-900/30 p-3 text-sm text-red-300">
          {clientErrors.map((err, i) => (
            <p key={i}>{err}</p>
          ))}
        </div>
      )}
    </div>
  );
}
