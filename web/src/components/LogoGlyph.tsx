// The logo's dotted i, which stands in for the first letter of the wordmark
// everywhere it is written: the front page and editorial pages (home/chrome),
// the report, search and history screens (Header), and the extension popup
// (extension/popup.html, kept in step by hand). Same paths as app/icon.svg.
export default function LogoGlyph({ className }: { className?: string }) {
  return (
    <svg viewBox="380 160 270 670" aria-hidden="true" className={className}>
      <circle cx="544" cy="260" r="92" fill="#c0392b" />
      <path
        fill="currentColor"
        d="M450 398C478 382 530 378 560 402C588 425 585 465 565 505L492 632C478 658 485 690 510 705C527 715 545 715 560 710L583 795C555 815 525 823 497 822C450 821 410 800 393 760C378 723 385 670 405 630L478 492C492 465 485 448 470 440C460 434 446 432 436 433Z"
      />
    </svg>
  )
}
