/** @odoo-module **/
import { Component, onWillStart, onWillUpdateProps, useState } from '@odoo/owl';
import { useBus, useService } from '@web/core/utils/hooks';
import { Domain } from '@web/core/domain';
import { _t } from '@web/core/l10n/translation';

export class BackendListFilters extends Component {
    static props = { context: { type: Object, optional: true }, baseDomain: { type: Array, optional: true }, revision: { type: String, optional: true } };
    setup() {
        this.orm = useService('orm');
        this.filters = this.constructor.filterConfig;
        this.data = useState({ cards: [] });
        this.countRequest = 0;
        this.countScope = '';
        useBus(this.env.searchModel, 'update', () => { this.render(); this.refreshCounts(); });
        onWillUpdateProps(next => this.refreshCounts(next, true));
        onWillStart(async () => {
            const cards = this.filters.requestKind
                ? await this.orm.call('employee.portal.backend.filter.card', 'get_dashboard_cards', [this.filters.requestKind])
                : this.constructor.getCards(this.props.context || {});
            this.data.cards.splice(0, this.data.cards.length, ...cards.map((card, index) => ({...card, key: String(card.id || index), label: _t(card.label), style: card.style || this.constructor.cardColors?.[card.label] || 'neutral', count: card.count ?? null})));
            await this.refreshCounts(this.props, true);
        });
    }
    async refreshCounts(props = this.props, force = false) {
        if (!this.data.cards.length) return;
        const inputs = this.env.searchModel.getSearchItems(item => item.absarListInput && item.isActive);
        const base = Domain.and([props.baseDomain || [], ...inputs.map(item => [[this.inputs.find(input => input.key === item.absarListInput).field, this.inputs.find(input => input.key === item.absarListInput).operator || 'ilike', item.absarListValue]])]).toList();
        const scope = JSON.stringify([base, props.context]);
        if (!force && scope === this.countScope) return;
        this.countScope = scope;
        const request = ++this.countRequest;
        try {
            const counts = await this.orm.call(this.filters.model, 'get_backend_card_counts', [this.data.cards.map(card => card.domain || []), base], {context: props.context || {}});
            if (request === this.countRequest) this.data.cards.forEach((card, index) => {card.count = counts[index];});
        } catch {
            if (request === this.countRequest) this.data.cards.forEach(card => {card.count = null;});
        }
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
