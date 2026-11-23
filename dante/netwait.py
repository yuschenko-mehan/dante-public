import socket
import time

HOSTS = (("1.1.1.1", 443), ("8.8.8.8", 53), ("github.com", 443))


def _connect(host, port, timeout):
    with socket.create_connection((host, port), timeout=timeout):
        return True


def online(connect=_connect, timeout=3.0):
    for h, p in HOSTS:
        try:
            if connect(h, p, timeout):
                return True
        except OSError:
            continue
    return False


def wait_for_network(probe=online, sleep=time.sleep, now=time.monotonic, say=print, timeout=600, interval=10):
    start, last_note = now(), None
    while True:
        if probe():
            if last_note is not None:
                say("Мережа є, продовжую / network is up")
            return True
        waited = now() - start
        if waited >= timeout:
            say(f"Мережі немає {int(waited)} с — стартую без мережі (локальні моделі працюють) / starting offline")
            return False
        if last_note is None or waited - last_note >= 60:
            say(f"Чекаю мережу… {int(waited)} с / waiting for the network")
            last_note = waited
        sleep(interval)


class NetPulse:
    """Network pulse: up -> check every 30 min, down -> every minute; log only on change.
    Пульс мережі: є -> раз на 30 хв, немає -> щохвилини; у журнал лише зміна стану."""

    def __init__(self, probe=online, say=print, now=time.monotonic, online_every=1800, offline_every=60,
                 status_file=None, state=None, next_at=None):
        self.probe, self.say, self.now = probe, say, now
        self.online_every, self.offline_every = online_every, offline_every
        self.status_file, self.state = status_file, state
        self.next_at = now() if next_at is None else next_at
        self.probes = 0

    def tick(self):
        t = self.now()
        if t < self.next_at:
            return None                      # not due: no probe / ще не час: мережу не чіпаємо
        try:
            up = bool(self.probe())
        except Exception:
            up = False                       # a broken probe means down / збій перевірки = мережі немає
        self.probes += 1
        self.next_at = t + (self.online_every if up else self.offline_every)
        if self.state is not None and up != self.state:
            self.say("мережа повернулась / network is back" if up
                     else f"мережа пропала, перевіряю щохвилини / network lost, checking every {self.offline_every} s")
        self.state = up
        if self.status_file:
            try:
                from pathlib import Path
                Path(self.status_file).write_text(("up " if up else "down ") + time.strftime("%Y-%m-%d %H:%M:%S"),
                                                  encoding="utf-8")
            except OSError:
                pass
        return up
