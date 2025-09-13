'use client';

import { useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { Upload, File as FileIcon, X } from 'lucide-react';

type DataDropProps = {
  className?: string;
};

type DroppedFile = {
  name: string;
  size: number;
  type: string;
  file: File;
};

export function DataDrop({ className }: DataDropProps) {
  const [files, setFiles] = useState<DroppedFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  }

  function addFiles(list: FileList | File[]) {
    const arr = Array.from(list).map((file) => ({
      name: file.name,
      size: file.size,
      type: file.type,
      file,
    }));
    setFiles((prev) => [...prev, ...arr]);
  }

  function onBrowseClick() {
    inputRef.current?.click();
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files); 
      e.currentTarget.value = '';
    }
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(true);
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
      e.dataTransfer.clearData();
    }
  }

  function removeAt(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  return (
    <div className={cn('bg-card flex h-full flex-col', className)}>
      <div className="px-6 pt-6 pb-4">
        <h2 className="text-2xl">Personal Context</h2>
        <p className="text-muted-foreground font-mono text-xs tracking-wider uppercase">
          CV-papers-projects
        </p>
      </div>

      <div className="min-h-0 flex-1 px-6 pb-6">
        <div
          role="button"
          tabIndex={0}
          onClick={onBrowseClick}
          onDragOver={onDragOver}
          onDragLeave={onDragLeave}
          onDrop={onDrop}
          className={cn(
            'border-border h-full w-full cursor-pointer rounded-md border transition-colors',
            'bg-accent flex min-h-0 flex-col overflow-hidden p-4',
            isDragOver ? 'border-primary bg-primary/5' : 'border-border',
          )}
        >
          {files.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-center">
              <div>
                <Upload className="text-muted-foreground mx-auto mb-2" size={20} />
                <p className="text-muted-foreground text-sm">
                  Drop pdf files here or click to browse
                </p>
              </div>
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="border-border min-h-0 flex-1 overflow-y-auto border-t border-b">
                <ul className="space-y-2">
                  {files.map((f, i) => (
                    <li
                      key={`${f.name}-${i}`}
                      className="border-border bg-card/50 flex items-center justify-between gap-3 rounded border p-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="flex min-w-0 items-center gap-2">
                        <FileIcon className="text-muted-foreground shrink-0" size={16} />
                        <div className="min-w-0">
                          <p className="text-foreground truncate text-sm">{f.name}</p>
                          <p className="text-muted-foreground text-xs">{formatBytes(f.size)}</p>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          removeAt(i);
                        }}
                        className="text-muted-foreground hover:text-destructive hover:bg-destructive/10 inline-flex cursor-pointer items-center justify-center rounded-sm p-1"
                        aria-label={`Remove ${f.name}`}
                      >
                        <X size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="mt-4 flex-shrink-0 text-center">
                <p className="text-muted-foreground text-xs">
                  Drop more files here or click to add
                </p>
              </div>
            </div>
          )}

          <input ref={inputRef} type="file" multiple onChange={onInputChange} className="hidden" />
        </div>
      </div>
    </div>
  );
}
