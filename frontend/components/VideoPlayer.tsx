"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";

export interface VideoPlayerHandle {
  seekTo: (seconds: number) => void;
}

const VideoPlayer = forwardRef<VideoPlayerHandle, { src: string }>(function VideoPlayer(
  { src },
  ref,
) {
  const video = useRef<HTMLVideoElement>(null);

  useImperativeHandle(ref, () => ({
    seekTo(seconds: number) {
      const el = video.current;
      if (!el) return;
      el.currentTime = seconds;
      el.play().catch(() => {
        // Autoplay can be blocked by the browser; the player stays at the new time.
      });
    },
  }));

  return (
    <video
      ref={video}
      src={src}
      controls
      preload="metadata"
      playsInline
      className="aspect-video w-full rounded-lg bg-black"
    />
  );
});

export default VideoPlayer;
