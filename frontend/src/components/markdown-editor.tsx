"use client";

/**
 * Milkdown Markdown 实时预览编辑器封装。
 *
 * 基于 @milkdown/crepe（开箱即用的 WYSIWYG 编辑器，内置工具栏）。
 * 半受控模式：defaultValue 仅在编辑器创建时设初值；
 * 用户编辑通过 onChange 回调向上通知 Markdown 字符串。
 * 仅 client 端渲染（ProseMirror 不支持 SSR）。
 */
import { useRef, useEffect } from "react";
import { Crepe } from "@milkdown/crepe";
import { Milkdown, MilkdownProvider, useEditor } from "@milkdown/react";
import "@milkdown/crepe/theme/common/style.css";
import "@milkdown/crepe/theme/frame.css";

interface MarkdownEditorProps {
  /** 编辑器初始内容（Markdown 字符串）。仅首次渲染生效。 */
  defaultValue: string;
  /** 用户编辑时回调，返回最新 Markdown 字符串。 */
  onChange?: (markdown: string) => void;
  placeholder?: string;
  readOnly?: boolean;
  className?: string;
}

function MilkdownEditorInner({
  defaultValue,
  onChange,
  placeholder,
  readOnly = false,
}: Omit<MarkdownEditorProps, "className">) {
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const { loading } = useEditor((root) => {
    const crepe = new Crepe({
      root,
      defaultValue,
      featureConfigs: {
        placeholder: placeholder ? { text: placeholder } : undefined,
      },
    });

    crepe.on((listeners) => {
      listeners.markdownUpdated((_ctx, markdown) => {
        onChangeRef.current?.(markdown);
      });
    });

    crepe.create().then(() => {
      crepe.setReadonly(readOnly);
    });

    return crepe;
  }, []);

  return <Milkdown />;
}

export default function MarkdownEditor({
  defaultValue,
  onChange,
  placeholder,
  readOnly,
  className,
}: MarkdownEditorProps) {
  return (
    <div className={className} data-loading={false}>
      <MilkdownProvider>
        <MilkdownEditorInner
          defaultValue={defaultValue}
          onChange={onChange}
          placeholder={placeholder}
          readOnly={readOnly}
        />
      </MilkdownProvider>
    </div>
  );
}
