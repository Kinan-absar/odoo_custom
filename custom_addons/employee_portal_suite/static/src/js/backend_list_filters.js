/** @odoo-module **/
import { Component, onWillStart, useState } from '@odoo/owl';
import { useBus, useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

export class BackendListFilters extends Component {
    static props = { context: { type: Object, optional: true } };
    setup() {
        this.orm = useService('orm');
        this.filters = this.constructor.filterConfig;
        this.data = useState({ cards: [] });
        useBus(this.env.searchModel, 'update', () => this.render());
        onWillStart(async () => {
            const cards = this.filters.requestKind
                ? await this.orm.call('employee.portal.backend.filter.card', 'get_dashboard_cards', [this.filters.requestKind])
                : this.constructor.getCards(this.props.context || {});
            this.data.cards.splice(0, this.data.cards.length, ...cards.map((card, index) => ({...card, key: String(card.id || index), label: _t(card.label)})));
        });
    }
    get inputs() { return this.filters.inputs; }
    get activeCard() {
        const items = this.env.searchModel.getSearchItems(item => item.absarListCard && item.isActive);
        return items.length ? items[0].absarListCard : null;
    }
    isActive(card) { return this.activeCard === null ? !(card.domain || []).length : this.activeCard === card.key; }
    selectCard(card) {
        const search = this.env.searchModel;
        for (const item of search.getSearchItems(item => item.absarListCard && item.isActive)) search.toggleSearchItem(item.id);
        if (card.domain && card.domain.length) search.createNewFilters([{description: card.label, domain: card.domain, absarListCard: card.key}]);
    }
    inputValue(key) {
        const items = this.env.searchModel.getSearchItems(item => item.absarListInput === key && item.isActive);
        return items.length ? items[0].absarListValue : '';
    }
    applyInput(input, rawValue) {
        const search = this.env.searchModel;
        for (const item of search.getSearchItems(item => item.absarListInput === input.key && item.isActive)) search.toggleSearchItem(item.id);
        const value = rawValue.trim();
        if (!value) return;
        search.createNewFilters([{description: `${_t(input.label)}: ${value}`, domain: [[input.field, input.operator || 'ilike', value]], absarListInput: input.key, absarListValue: value}]);
    }
}
