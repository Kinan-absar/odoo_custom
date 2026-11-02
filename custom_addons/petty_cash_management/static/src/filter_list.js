/** @odoo-module **/
import { registry } from '@web/core/registry';
import { useBus } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';
import { listView } from '@web/views/list/list_view';
import { ListRenderer } from '@web/views/list/list_renderer';

export class PettyCashFilterRenderer extends ListRenderer {
    static template = 'petty_cash_management.FilterList';
    setup() {
        super.setup();
        this.cards = [
            { key: 'all', label: _t('All Reports'), domain: [] },
            { key: 'draft', label: _t('Draft'), domain: [['state', '=', 'draft']] },
            { key: 'submitted', label: _t('Accounting Review'), domain: [['state', '=', 'submitted']] },
            { key: 'review_2', label: _t('Supervisor Review'), domain: [['state', '=', 'review_2']] },
            { key: 'manager_approval', label: _t('Manager Approval'), domain: [['state', '=', 'manager_approval']] },
            { key: 'approved', label: _t('Approved'), domain: [['state', '=', 'approved']] },
            { key: 'ready', label: _t('Ready for Voucher'), domain: [['state', '=', 'approved'], ['journal_entry_id', '=', false]] },
            { key: 'voucher', label: _t('Voucher Created'), domain: [['journal_entry_id', '!=', false]] },
            { key: 'refused', label: _t('Refused'), domain: [['state', '=', 'refused']] },
        ];
        useBus(this.env.searchModel, 'update', () => this.render());
    }
    get activeCard() {
        const active = this.env.searchModel.getSearchItems(item => item.pettyCashCard && item.isActive);
        return active.length ? active[0].pettyCashCard : 'all';
    }
    selectCard(card) {
        const search = this.env.searchModel;
        for (const filter of search.getSearchItems(item => item.pettyCashCard && item.isActive)) {
            search.toggleSearchItem(filter.id);
        }
        if (card.key !== 'all') {
            search.createNewFilters([{ description: card.label, domain: card.domain, pettyCashCard: card.key }]);
        }
    }
    dimensionValue(key) {
        const items = this.env.searchModel.getSearchItems(item => item.pettyCashDimension === key && item.isActive);
        return items.length ? items[0].pettyCashValue : '';
    }
    applyDimension(key, label, value) {
        const search = this.env.searchModel;
        for (const filter of search.getSearchItems(item => item.pettyCashDimension === key && item.isActive)) {
            search.toggleSearchItem(filter.id);
        }
        value = value.trim();
        if (!value) return;
        const domains = {
            submitter: [['user_id.name', 'ilike', value]],
            project: ['|', ['line_ids.zone', 'ilike', value], ['line_ids.category_id.analytic_account_id.name', 'ilike', value]],
            from: [['date', '>=', value]],
            to: [['date', '<=', value]],
        };
        search.createNewFilters([{ description: `${label}: ${value}`, domain: domains[key], pettyCashDimension: key, pettyCashValue: value }]);
    }
}
registry.category('views').add('petty_cash_filter_list', { ...listView, Renderer: PettyCashFilterRenderer });
