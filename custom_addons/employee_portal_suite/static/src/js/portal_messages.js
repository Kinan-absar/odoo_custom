odoo.define('employee_portal_suite.portal_messages', [], function (require) {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const chatBox = document.getElementById('eps_chat_messages');
        if (chatBox) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    });
});
