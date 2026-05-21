odoo.define('employee_portal_suite.portal_messages', [], function (require) {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        const chatBox = document.getElementById('ep_chat_box');
        if (chatBox) {
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    });
});
