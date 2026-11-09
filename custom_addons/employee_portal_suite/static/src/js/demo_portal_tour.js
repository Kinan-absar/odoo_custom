/** @odoo-module **/

const STORAGE_KEY = 'eps_demo_portal_tour_step';
const OPEN_KEY = 'eps_demo_portal_tour_open';

const steps = [
    {
        title: 'Welcome to Employee Portal',
        url: '/my/employee',
        selector: '.dashboard-card, .needs-attention',
        text: 'This is the employee self-service home. From here an employee can reach requests, materials, attendance, reports, approvals and communication according to the access assigned by the administrator.'
    },
    {
        title: 'Employee Requests',
        url: '/my/employee/requests',
        selector: 'a[href="/my/employee/requests/new"]',
        text: 'Employees can create and follow their own requests. Click New Request to submit a request into the Manager → HR → Finance → CEO approval workflow.'
    },
    {
        title: 'Create an Employee Request',
        url: '/my/employee/requests/new',
        selector: 'form, .card',
        text: 'This is the employee request form. The employee fills the request and submits it; every approval stage and status is then visible from the portal.'
    },
    {
        title: 'Material Requests',
        url: '/my/employee/material',
        selector: 'a[href="/my/employee/material/new"]',
        text: 'Material Requests are also available directly from the portal. Employees can create a request and track it through the configured purchase, store, project and management approval roles.'
    },
    {
        title: 'Create a Material Request',
        url: '/my/employee/material/new',
        selector: 'form, .card',
        text: 'Here the employee selects the worksite/project information and enters the required materials. Submit a sample request if you want to test the complete approval flow.'
    },
    {
        title: 'Attendance & Work Location',
        url: '/my/employee/attendance',
        selector: '#checkin-btn, #checkout-btn, .attendance-hero',
        text: 'Attendance uses the employee Work Location and its project/geolocation configuration. The employee can Check In and Check Out only according to the rules configured by the company.'
    },
    {
        title: 'Portal Reports',
        url: '/my/employee/reports',
        selector: '.portal-report-table-card, .alert-info',
        text: 'Reports and PDF documents can be shared with selected portal groups. Each employee only sees the reports made available to their access group.'
    },
    {
        title: 'Announcements',
        url: '/my/employee',
        selector: '.portal-announcement, .portal-announcement-wrapper',
        text: 'Company announcements appear directly inside the employee portal and can be targeted to selected groups. Attachments can also be shared with the announcement.'
    },
    {
        title: 'Messages, Calls & Channels',
        url: '/my/employee/discuss',
        selector: '.o-mail-Discuss, .o-mail-ChatWindow, main, #wrap',
        text: 'The portal includes integrated Discuss. Employees can use direct messages and permitted channels, and can use attachments, voice notes and calls without becoming internal Odoo users.'
    },
    {
        title: 'Browser Notifications',
        url: '/my/employee',
        selector: '.ep-bell-btn, .ep-bell-wrap',
        text: 'Use the notification bell to enable browser notifications. Messages, calls, approvals, attendance events and other Employee Portal notifications can then reach the employee even when they are not actively viewing the page.'
    },
    {
        title: 'Tour Complete',
        url: '/my/employee',
        selector: '.ep-sidebar-profile, .mobile-app-header',
        text: 'You have now seen the main employee experience. Feel free to create, edit and test anything in this temporary demo. Switch back to the Manager account to review and approve the records you submitted.'
    },
];

function pathMatches(url) {
    const wanted = new URL(url, window.location.origin).pathname.replace(/\/$/, '');
    const current = window.location.pathname.replace(/\/$/, '');
    return wanted === current;
}

function removeHighlight() {
    document.querySelectorAll('.eps-portal-tour-highlight').forEach((el) => el.classList.remove('eps-portal-tour-highlight'));
}

function highlight(selector) {
    removeHighlight();
    if (!selector) return;
    let el = null;
    try {
        const candidates = document.querySelectorAll(selector);
        el = Array.from(candidates).find((node) => node.offsetParent !== null) || candidates[0];
    } catch (_) {
        return;
    }
    if (!el) return;
    el.classList.add('eps-portal-tour-highlight');
    setTimeout(() => {
        try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (_) {}
    }, 180);
}

function buildWidget(root) {
    root.innerHTML = `
        <button type="button" class="eps-portal-tour-launcher" aria-label="Employee Portal Tour">
            <i class="fa fa-compass"></i><span>Portal Tour</span>
        </button>
        <section class="eps-portal-tour-panel" aria-live="polite">
            <header>
                <div><small>EMPLOYEE PORTAL DEMO</small><strong class="eps-tour-title"></strong></div>
                <button type="button" class="eps-tour-close" aria-label="Close"><i class="fa fa-times"></i></button>
            </header>
            <div class="eps-tour-progress"><span></span></div>
            <div class="eps-tour-step-label"></div>
            <p class="eps-tour-text"></p>
            <div class="eps-tour-actions">
                <button type="button" class="btn btn-light eps-tour-back"><i class="fa fa-chevron-left me-1"></i>Back</button>
                <button type="button" class="btn btn-outline-primary eps-tour-open">Open This Step</button>
                <button type="button" class="btn btn-primary eps-tour-next">Next<i class="fa fa-chevron-right ms-1"></i></button>
            </div>
        </section>`;

    const launcher = root.querySelector('.eps-portal-tour-launcher');
    const panel = root.querySelector('.eps-portal-tour-panel');
    const close = root.querySelector('.eps-tour-close');
    const back = root.querySelector('.eps-tour-back');
    const next = root.querySelector('.eps-tour-next');
    const open = root.querySelector('.eps-tour-open');

    const getStep = () => Math.max(0, Math.min(steps.length - 1, parseInt(sessionStorage.getItem(STORAGE_KEY) || '0', 10) || 0));
    const setStep = (value) => sessionStorage.setItem(STORAGE_KEY, String(Math.max(0, Math.min(steps.length - 1, value))));

    function render() {
        const index = getStep();
        const step = steps[index];
        root.querySelector('.eps-tour-title').textContent = step.title;
        root.querySelector('.eps-tour-step-label').textContent = `Step ${index + 1} of ${steps.length}`;
        root.querySelector('.eps-tour-text').textContent = step.text;
        root.querySelector('.eps-tour-progress span').style.width = `${((index + 1) / steps.length) * 100}%`;
        back.disabled = index === 0;
        next.innerHTML = index === steps.length - 1 ? 'Finish' : 'Next<i class="fa fa-chevron-right ms-1"></i>';
        open.style.display = pathMatches(step.url) ? 'none' : '';
        if (pathMatches(step.url)) setTimeout(() => highlight(step.selector), 260);
        else removeHighlight();
    }

    function openPanel() {
        panel.classList.add('show');
        launcher.classList.add('hidden');
        sessionStorage.setItem(OPEN_KEY, '1');
        render();
    }

    function closePanel() {
        panel.classList.remove('show');
        launcher.classList.remove('hidden');
        sessionStorage.setItem(OPEN_KEY, '0');
        removeHighlight();
    }

    function navigateTo(index) {
        setStep(index);
        sessionStorage.setItem(OPEN_KEY, '1');
        const step = steps[index];
        if (!pathMatches(step.url)) window.location.assign(step.url);
        else render();
    }

    launcher.addEventListener('click', openPanel);
    close.addEventListener('click', closePanel);
    back.addEventListener('click', () => navigateTo(getStep() - 1));
    open.addEventListener('click', () => navigateTo(getStep()));
    next.addEventListener('click', () => {
        const index = getStep();
        if (index >= steps.length - 1) {
            sessionStorage.removeItem(STORAGE_KEY);
            closePanel();
            return;
        }
        navigateTo(index + 1);
    });

    if (sessionStorage.getItem(OPEN_KEY) === '1') openPanel();
    else render();
}

function init() {
    const marker = document.getElementById('eps-demo-portal-tour-marker');
    if (!marker || document.getElementById('eps-demo-portal-tour-widget')) return;
    const root = document.createElement('div');
    root.id = 'eps-demo-portal-tour-widget';
    document.body.appendChild(root);
    buildWidget(root);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
else init();
