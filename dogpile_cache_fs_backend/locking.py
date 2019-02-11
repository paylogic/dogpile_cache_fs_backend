import errno
import logging
import threading

from dogpile.cache import util

logger = logging.getLogger(__name__)


class RangedFileReentrantLock(object):
    def __init__(self, file_, offset):
        if file_ is None:
            raise TypeError('file parameter cannot be None')
        self._offset = offset
        self._file = file_
        self._thread_lock = threading.RLock()
        self._counter = 0

    def is_locked(self):
        return self._counter > 0

    @util.memoized_property
    def _module(self):
        import fcntl
        return fcntl

    def acquire(self, blocking=True):
        lockflag = self._module.LOCK_EX
        if not blocking:
            lockflag |= self._module.LOCK_NB
        acquired = self._thread_lock.acquire(blocking)
        if not blocking and not acquired:
            return False

        if self._counter == 0:
            try:
                logger.debug('lockf({}, blocking={}, offset={})'.format(
                    getattr(self._file, 'name', self._file), blocking, self._offset
                ))
                if self._offset is not None:
                    self._module.lockf(self._file, lockflag, 1, self._offset)
                else:
                    self._module.lockf(self._file, lockflag)
                logger.debug('! lockf({}, blocking={}, offset={})'.format(
                    getattr(self._file, 'name', self._file), blocking, self._offset
                ))
            except IOError as e:
                self._thread_lock.release()
                if e.errno in (errno.EACCES, errno.EAGAIN):
                    return False
                raise

        self._counter += 1
        return True

    def release(self):
        self._counter -= 1
        assert self._counter >= 0
        if self._counter > 0:
            self._thread_lock.release()
            return

        try:
            logger.debug('unlockf({}, offset={})'.format(
                getattr(self._file, 'name', self._file), self._offset
            ))
            if self._offset is not None:
                self._module.lockf(self._file, self._module.LOCK_UN, 1, self._offset)
            else:
                self._module.lockf(self._file, self._module.LOCK_UN)
        finally:
            # DO NOT assign self._file to None. Otherwise in case this object is not dereferenced, nobody else can do
            # acquire on it after the last release.
            # self._file = None
            self._thread_lock.release()

    def __enter__(self):
        self.acquire(blocking=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
