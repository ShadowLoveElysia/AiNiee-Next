import { useEffect, useState } from 'react';
import { t } from '../i18n';
import { ArrowDown, ArrowUp, Pencil, Trash2 } from 'lucide-react';
import type { QueueItem } from '../api/contracts';

export function QueueItemActions({ item, disabled, canMoveUp, canMoveDown, remove, move, edit }: {
  item: QueueItem;
  disabled: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  remove: () => Promise<boolean>;
  move: (direction: -1 | 1) => Promise<boolean>;
  edit: () => void;
}) {
  const [confirmRemove, setConfirmRemove] = useState(false);
  useEffect(() => { setConfirmRemove(false); }, [item.revision]);
  return <div className="queue-item-actions">
    <button type="button" className="text-button" disabled={disabled} onClick={edit}><Pencil size={15} />{t('gui.queue.edit')}</button>
    <button type="button" className="text-button" disabled={disabled || !canMoveUp} onClick={() => void move(-1)}><ArrowUp size={15} />{t('gui.queueActions.up')}</button>
    <button type="button" className="text-button" disabled={disabled || !canMoveDown} onClick={() => void move(1)}><ArrowDown size={15} />{t('gui.queueActions.down')}</button>
    {confirmRemove ? <div className="queue-remove-confirm" role="group" aria-label={t('gui.queueActions.remove_title')}>
      <span>{t('gui.queueActions.remove_question')}</span>
      <button type="button" className="text-button danger-button" disabled={disabled} onClick={() => void remove().then((success) => { if (success) setConfirmRemove(false); })}>{t('gui.queueActions.confirm_remove')}</button>
      <button type="button" className="text-button" onClick={() => setConfirmRemove(false)}>{t('gui.common.cancel')}</button>
    </div> : <button type="button" className="text-button danger-button" disabled={disabled} onClick={() => setConfirmRemove(true)}><Trash2 size={15} />{t('gui.queueActions.remove')}</button>}
  </div>;
}
