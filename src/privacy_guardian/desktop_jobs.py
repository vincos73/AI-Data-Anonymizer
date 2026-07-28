from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


ResultT = TypeVar("ResultT")
ProgressCallback = Callable[[int, str], None]


class OperationCancelled(RuntimeError):
    """Raised cooperatively when a desktop operation has been cancelled."""


class CancellationToken:
    def __init__(self) -> None:
        self._cancelled = Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise OperationCancelled("Operazione annullata.")


@dataclass(frozen=True)
class JobContext:
    token: CancellationToken
    progress_callback: ProgressCallback

    def progress(self, value: int, message: str) -> None:
        self.token.raise_if_cancelled()
        self.progress_callback(max(0, min(100, value)), message)

    def check_cancelled(self) -> None:
        self.token.raise_if_cancelled()


class JobSignals(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()
    finished = Signal()


class DesktopJob(QRunnable, Generic[ResultT]):
    def __init__(self, work: Callable[[JobContext], ResultT]) -> None:
        super().__init__()
        self.work = work
        self.token = CancellationToken()
        self.signals = JobSignals()
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.token.cancel()

    @Slot()
    def run(self) -> None:
        context = JobContext(self.token, self.signals.progress.emit)
        try:
            context.check_cancelled()
            result = self.work(context)
            context.check_cancelled()
        except OperationCancelled:
            self.signals.cancelled.emit()
        except Exception as exc:
            self.signals.failed.emit(exc)
        else:
            self.signals.succeeded.emit(result)
        finally:
            self.signals.finished.emit()
