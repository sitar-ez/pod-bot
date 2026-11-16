"""
Setup check. Run it from GitHub: Actions > "Check setup" > Run workflow.
It tests every connection and tells you (in the log and on Telegram) what's
working and what still needs doing. Changes nothing.
"""
import os

from . import printful, settings, telegram
from .common import load_state, log


def main():
    report, state = [], load_state()

    def ok(msg):
        report.append(f"✅ {msg}")

    def bad(msg):
        report.append(f"❌ {msg}")

    for name in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "PRINTFUL_TOKEN", "ETSY_KEYSTRING",
                 "ETSY_SHARED_SECRET", "ETSY_REFRESH_TOKEN", "TELEGRAM_BOT_TOKEN"]:
        (ok if os.getenv(name) else bad)(f"secret {name} {'is set' if os.getenv(name) else 'is MISSING'}")

    try:
        from . import llm
        llm.client().messages.create(model=settings.CLAUDE_MODEL, max_tokens=5,
                                     messages=[{"role": "user", "content": "hi"}])
        ok(f"Claude works ({settings.CLAUDE_MODEL})")
    except Exception as e:
        bad(f"Claude: {e}")

    try:
        for key in settings.PRODUCTS:
            info = printful.resolve_product(key, state)
            ok(f"Printful {key}: {info['title']} with {len(info['variants'])} variants")
    except Exception as e:
        bad(f"Printful: {e}")

    try:
        from .etsy import Etsy
        from .publisher import shop_setup
        e = Etsy()
        ok(f"Etsy sign-in works (shop id {e.shop_id})")
        c = shop_setup(e, state)
        ok(f"Etsy shipping profile {c['shipping_profile_id']}, processing profile {c['readiness_state_id']}, "
           f"Printful partner {c['production_partner_ids']}")
        for k, t in c["taxonomy"].items():
            (ok if t else bad)(f"Etsy category for {k}: {t}")
    except Exception as e:
        bad(f"Etsy: {e}")

    try:
        ok(f"Telegram chat found ({telegram.chat_id()})")
    except Exception as e:
        bad(f"Telegram: {e}")

    report.append(f"\nDry run is {'ON (safe mode)' if settings.DRY_RUN else 'OFF (live)'}")
    text = "Setup check\n\n" + "\n".join(report)
    log(text)
    telegram.send(text)


if __name__ == "__main__":
    main()
