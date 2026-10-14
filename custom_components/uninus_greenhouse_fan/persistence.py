"""Verified Store transactions with a restart-visible fail-closed journal."""
import asyncio
from copy import deepcopy
import json
import logging
from pathlib import Path

_LOGGER = logging.getLogger(__name__)


class StorageQuarantined(OSError):
    """Durability is indeterminate; this group must not control equipment."""


class VerifiedStore:
    def __init__(self, hass, store, loaded, fail_closed):
        self.hass, self.store = hass, store
        self.previous = deepcopy(loaded)
        self.fail_closed = fail_closed
        self.path = Path(store.path) if hasattr(store, 'path') else None
        self.pending = Path(str(self.path) + '.pending') if self.path else None

    def check_quarantine(self):
        # stat errors must fail setup too, not masquerade as an absent journal.
        if self.pending:
            try:
                self.pending.stat()
            except FileNotFoundError:
                return
            raise StorageQuarantined(f'Storage quarantined: restore previous record from {self.pending}; see recovery documentation')

    def envelope(self, payload):
        return {'version': self.store.version, 'minor_version': self.store.minor_version,
                'key': self.store.key, 'data': payload}

    def _prepare(self):
        from homeassistant.util.file import write_utf8_file_atomic
        self.pending.parent.mkdir(parents=True, exist_ok=True)
        journal = {'previous': self.envelope(self.previous) if self.previous is not None else None}
        write_utf8_file_atomic(str(self.pending), json.dumps(journal))
        if json.loads(self.pending.read_text(encoding='utf-8')) != journal:
            raise OSError('Transaction journal verification failed')

    def _read(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    async def _verify(self, payload):
        for _ in range(3):
            try:
                if await self.hass.async_add_executor_job(self._read) == self.envelope(payload):
                    return
            except (OSError, ValueError, KeyError):
                pass
        raise OSError('Stored device settings could not be verified after three reads')

    def _restore(self):
        # Do not use Store here: it can defer a rollback until final-write during shutdown.
        from homeassistant.util.file import write_utf8_file_atomic
        if self.previous is None:
            self.path.unlink(missing_ok=True)
        else:
            write_utf8_file_atomic(str(self.path), json.dumps(self.envelope(self.previous)))

    async def _rollback(self):
        # If an atomic write was swallowed but old bytes are still there, avoid
        # rewriting them (the writer may still be unavailable).
        try:
            await self._verify(self.previous)
        except OSError:
            await self.hass.async_add_executor_job(self._restore)
            if self.previous is not None:
                await self._verify(self.previous)
            else:
                await self.hass.async_add_executor_job(self._verify_absent)
        await self.hass.async_add_executor_job(self.pending.unlink)

    def _verify_absent(self):
        try:
            self.path.stat()
        except FileNotFoundError:
            return
        raise OSError('Rollback did not remove the newly created storage file')

    def _quarantine(self, error):
        self.fail_closed()
        _LOGGER.critical('Fan group storage quarantined at %s. Control disabled; restore journal previous record before removing .pending and reloading. Error: %s', self.pending, error)
        return StorageQuarantined(f'Storage quarantined at {self.pending}; control disabled; restore previous record before reloading')

    async def _transaction(self, payload):
        try:
            await self.hass.async_add_executor_job(self._prepare)
        except Exception as error:
            # No candidate write was attempted, but a partial journal is still
            # conservative restart quarantine; do not silently delete it.
            raise self._quarantine(error) from error
        try:
            if getattr(getattr(self.hass, 'state', None), 'value', None) == 'STOPPING':
                raise OSError('Home Assistant is stopping; device writes are not accepted')
            await self.store.async_save(payload)
            await self._verify(payload)
        except Exception as error:
            try:
                await self._rollback()
            except Exception as rollback_error:
                raise self._quarantine(rollback_error) from error
            raise OSError('Save failed; previous durable record restored and verified') from error
        # Keep the journal until save() reaches its no-await publication boundary.

    async def save(self, payload):
        if getattr(getattr(self.hass, 'state', None), 'value', None) == 'STOPPING':
            raise OSError('Home Assistant is stopping; device writes are not accepted')
        if not self.path:  # Offline adapter fakes have no disk; real HA always does.
            await self.store.async_save(payload)
            self.previous = deepcopy(payload)
            return
        self.check_quarantine()
        task = asyncio.create_task(self._transaction(payload))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # A canceled await does not stop an executor write. Drain it before
            # restoring old bytes, holding the caller's registry/group locks.
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            error = task.exception()
            if error is None:
                rollback = asyncio.create_task(self._rollback())
                while not rollback.done():
                    try:
                        await asyncio.shield(rollback)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                if rollback.exception() is not None:
                    self._quarantine(rollback.exception())
            raise
        try:
            # One deliberately synchronous unlink: no cancellation/yield between
            # journal release and Registry's immediate in-memory publication.
            self.pending.unlink()
        except Exception as error:
            raise self._quarantine(error) from error
        self.previous = deepcopy(payload)
