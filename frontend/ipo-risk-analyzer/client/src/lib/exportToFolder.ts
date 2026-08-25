export function isDirectoryExportSupported(): boolean {
  return typeof window.showDirectoryPicker === "function";
}

export async function pickExportDirectory(): Promise<FileSystemDirectoryHandle | null> {
  if (!isDirectoryExportSupported()) return null;
  try {
    return await window.showDirectoryPicker({ mode: "readwrite" });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") return null;
    throw err;
  }
}

export async function writeBlobToDirectory(
  dir: FileSystemDirectoryHandle,
  filename: string,
  blob: Blob
): Promise<void> {
  const fileHandle = await dir.getFileHandle(filename, { create: true });
  const writable = await fileHandle.createWritable();
  await writable.write(blob);
  await writable.close();
}
