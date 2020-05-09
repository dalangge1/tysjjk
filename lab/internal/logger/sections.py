import math
import time
from typing import TYPE_CHECKING

from ...logger import Text

if TYPE_CHECKING:
    from . import Logger


class Section:
    r"""
        Note:
            You should use :meth:`lab.logger.section` to create sections
    """

    def __init__(self, *,
                 logger: 'Logger',
                 name: str,
                 is_silent: bool,
                 is_timed: bool,
                 is_partial: bool,
                 total_steps: float):
        self._logger = logger
        self._name = name
        self.is_silent = is_silent
        self._is_timed = is_timed
        self._is_partial = is_partial
        self._total_steps = total_steps

        self._state = 'none'
        self._has_entered_ever = False

        self._start_time = 0
        self._end_time = -1
        self._progress = 0.
        self._start_progress = 0
        self._end_progress = 0
        self._is_parented = False

        self.is_successful = True

    def get_estimated_time(self) -> float:
        raise NotImplementedError()

    def __enter__(self):
        self._state = 'entered'
        self._has_entered_ever = True
        self.is_successful = True

        if not self._is_partial:
            self._progress = 0

        self._start_progress = self._progress

        if self._is_timed:
            self._start_time = time.time()

        self._logger.section_enter(self)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._state = 'exited'
        if self._is_timed:
            self._end_time = time.time()

        if not self._is_partial:
            self._progress = 1.

        self._end_progress = self._progress

        self._logger.section_exit(self)

    def log(self):
        raise NotImplementedError()

    def progress(self, steps):
        old_progress = self._progress
        self._progress = steps / self._total_steps

        if self.is_silent:
            return False

        if math.floor(self._progress * 100) != math.floor(old_progress * 100):
            return True
        else:
            return False

    @property
    def is_parented(self):
        return self._is_parented

    def make_parent(self):
        self._is_parented = True


class OuterSection(Section):
    def __init__(self, *,
                 logger: 'Logger',
                 name: str,
                 is_silent: bool,
                 is_timed: bool,
                 is_partial: bool,
                 is_new_line: bool,
                 total_steps: float,
                 level: int):
        if is_partial:
            raise RuntimeError("Only sections within the loop can be partial.")

        super().__init__(logger=logger,
                         name=name,
                         is_silent=is_silent,
                         is_timed=is_timed,
                         is_partial=is_partial,
                         total_steps=total_steps)

        self._level = level
        self._is_new_line = is_new_line

    def get_estimated_time(self):
        if self._state is 'entered':
            if self._progress == 0.:
                return time.time() - self._start_time
            else:
                return (time.time() - self._start_time) / self._progress
        else:
            return self._end_time - self._start_time

    def log(self):
        if self.is_silent:
            return

        if self._state is 'none':
            return

        parts = [("  " * self._level + f"{self._name}", None)]

        if self._state == 'entered':
            if self._progress == 0.:
                parts.append("...")
            else:
                parts.append((f" {math.floor(self._progress * 100) :4.0f}%", Text.meta2))
        else:
            if self.is_successful:
                parts.append(("...[DONE]", Text.success))
            else:
                parts.append(("...[FAIL]", Text.danger))

        if self._is_timed and self._progress > 0.:
            duration_ms = 1000 * self.get_estimated_time()
            parts.append((f"\t{duration_ms :,.2f}ms",
                          Text.meta))

        if self._state != 'entered' and self._is_new_line:
            parts.append(("\n", None))

        return parts


class LoopingSection(Section):
    def __init__(self, *,
                 logger: 'Logger',
                 name: str,
                 is_silent: bool,
                 is_timed: bool,
                 is_partial: bool,
                 total_steps: float):
        super().__init__(logger=logger,
                         name=name,
                         is_silent=is_silent,
                         is_timed=is_timed,
                         is_partial=is_partial,
                         total_steps=total_steps)
        self._beta_pow = 1.
        self._beta = 0.9
        self._estimated_time = 0.
        self._time_length = 7
        self._last_end_time = -1.
        self._last_start_time = -1.
        self._last_step_time = 0.

    def get_estimated_time(self):
        et = self._estimated_time * self._beta
        et += (1 - self._beta) * self._last_step_time
        return et / (1 - self._beta_pow * self._beta)

    def _calc_estimated_time(self):
        if self._state != 'entered':
            if self._last_end_time == self._end_time:
                return self.get_estimated_time()
            end_time = self._end_time
            end_progress = self._end_progress
            self._last_end_time = self._end_time
        else:
            end_time = time.time()
            end_progress = self._progress

        if end_progress - self._start_progress < 1e-6:
            return self.get_estimated_time()

        current_estimate = ((end_time - self._start_time) /
                            (end_progress - self._start_progress))

        if self._last_start_time == self._start_time:
            # print(current_estimate)
            self._last_step_time = current_estimate
        else:
            if self._last_step_time >= 0.:
                self._beta_pow *= self._beta
                self._estimated_time *= self._beta
                self._estimated_time += (1 - self._beta) * self._last_step_time
            # print(self._last_step_time, current_estimate)
            self._last_step_time = current_estimate
            self._last_start_time = self._start_time

        return self.get_estimated_time()

    def log(self):
        if self.is_silent:
            return []

        if self._state == 'none':
            return []

        parts = [(f"{self._name}:", None)]
        color = None

        if not self.is_successful:
            color = Text.danger

        if self._progress == 0.:
            parts.append(("  ...", Text.subtle))
        else:
            parts.append((f"{math.floor(self._progress * 100) :4.0f}%",
                          color or Text.subtle))

        if self._is_timed:
            duration_ms = 1000 * self._calc_estimated_time()
            s = f" {duration_ms:,.0f}ms  "
            tl = len(s)
            if tl > self._time_length:
                self._time_length = tl
            else:
                s = (" " * (self._time_length - tl)) + s

            parts.append((s, color or Text.meta))

        return parts
