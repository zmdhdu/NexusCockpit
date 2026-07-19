/**
 * Copyright (c) 2026 zhangmengdi (NexusCockpit)
 * Licensed under the MIT License. See LICENSE in the project root for details.
 * Source: https://github.com/zmdhdu/NexusCockpit
 */

import * as React from "react";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

export interface DialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children?: React.ReactNode;
}

export const Dialog = React.forwardRef<HTMLDivElement, DialogProps>(
  ({ open, onOpenChange, children }, ref) => {
    if (!open) return null;

    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div
          ref={ref}
          className="relative w-full max-w-md rounded-lg bg-card p-6 shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => onOpenChange?.(false)}
            className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
          {children}
        </div>
      </div>
    );
  },
);

Dialog.displayName = "Dialog";

export const DialogHeader: React.FC<{ title?: string; description?: string }> = ({
  title,
  description,
}) => (
  <div className="mb-4">
    {title && <h3 className="text-lg font-semibold">{title}</h3>}
    {description && <p className="text-sm text-muted-foreground">{description}</p>}
  </div>
);

export const DialogContent = ({ children }: { children: React.ReactNode }) => (
  <div className="space-y-4">{children}</div>
);

export const DialogFooter: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="mt-6 flex justify-end gap-2">{children}</div>
);