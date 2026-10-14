export default function UploadNotice() {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
      <p className="font-medium">Upload only public stock videos.</p>
      <p className="mt-1">
        Frames may be sent to a third party AI model (on the Gemini free tier, Google may use them
        to improve its products). Never upload real plant footage or videos of people who did not
        agree to it.
      </p>
    </div>
  );
}
