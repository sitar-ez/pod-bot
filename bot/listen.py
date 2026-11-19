"""
Rory listens between runs. Instead of sleeping until the next run, Rory keeps a line open to
Telegram and answers your taps and messages within seconds, day and night. Anything that
changes (an approval, a skip, an edit, a lesson) is saved to GitHub right away, so the next
run picks it up. Usage: python -m bot.listen <seconds>
"""
import subprocess
import sys
import time
import traceback

from . import inbox, run, telegram
from .common import ROOT, load_state, log, save_state


def save_to_github(note):
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    git("add", "-A", "state", "designs", "inbox")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("-c", "user.name=pod-bot", "-c", "user.email=pod-bot@users.noreply.github.com", "commit", "-m", note)
    for _ in range(3):
        git("pull", "--rebase")
        if git("push").returncode == 0:
            return
        time.sleep(5)
    log("  could not save to GitHub; will retry after the next change")


def main(seconds):
    deadline = time.time() + seconds
    state = load_state()
    if state.get("telegram_chat_id"):
        telegram._found["id"] = state["telegram_chat_id"]
    from . import costs
    costs.STAGE["name"] = "Telegram replies"
    log(f"listening to Telegram for {int(seconds / 60)} minutes")
    while True:
        left = deadline - time.time()
        if left < 5:
            break
        try:
            ups = telegram.updates(state["telegram_offset"], wait=int(min(25, left)))
            if ups:
                run.handle_telegram(state, ups)
                save_state(state)
                save_to_github("bot: telegram replies")
            inbox.pull()   # dashboard button presses
            if inbox.process(state):
                save_state(state)
                save_to_github("bot: dashboard actions")
        except Exception as e:
            log("  listen error:", e)
            traceback.print_exc()
            time.sleep(10)
    log("done listening")


if __name__ == "__main__":
    main(float(sys.argv[1]))
