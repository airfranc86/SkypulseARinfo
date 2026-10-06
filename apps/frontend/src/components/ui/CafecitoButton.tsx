import {
  CAFECITO_BUTTON_ALT,
  CAFECITO_BUTTON_HEIGHT,
  CAFECITO_BUTTON_SRC,
  CAFECITO_BUTTON_SRCSET,
  CAFECITO_BUTTON_WIDTH,
  CAFECITO_URL,
} from '@/lib/siteLinks'

/**
 * Official Cafecito button (voluntary contribution, nothing is unlocked). The image is 40 px tall, so
 * the anchor adds vertical room to keep a 44 px touch target.
 */
export function CafecitoButton() {
  return (
    <a
      href={CAFECITO_URL}
      rel="noopener"
      target="_blank"
      className="inline-flex min-h-[44px] items-center px-1 hover:opacity-90"
    >
      <img
        srcSet={CAFECITO_BUTTON_SRCSET}
        src={CAFECITO_BUTTON_SRC}
        alt={CAFECITO_BUTTON_ALT}
        width={CAFECITO_BUTTON_WIDTH}
        height={CAFECITO_BUTTON_HEIGHT}
        loading="lazy"
        decoding="async"
      />
    </a>
  )
}
