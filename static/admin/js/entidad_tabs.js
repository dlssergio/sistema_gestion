// static/admin/js/entidad_tabs.js (Versión Final)
window.addEventListener('DOMContentLoaded', (event) => {
    const form = document.querySelector('#entidad_form');
    if (!form) return;

    setTimeout(() => {
        const submitRows = form.querySelectorAll('.submit-row');
        if (submitRows.length > 1) {
            submitRows[0].remove();
        }
    }, 100);

    const mainFieldset = form.querySelector('fieldset');
    const inlines = Array.from(form.querySelectorAll('.inline-group'));
    if (!mainFieldset && inlines.length === 0) return;

    const tabConfig = [
        { title: 'Datos Principales', content: [mainFieldset] },
        { title: 'Roles', content: inlines.filter(el => el && (el.id.includes('proveedor') || el.id.includes('cliente'))) },
        { title: 'Contacto', content: inlines.filter(el => el && (el.id.includes('domicilio') || el.id.includes('telefono') || el.id.includes('email'))) }
    ];

    const tabsContainer = document.createElement('ul');
    tabsContainer.className = 'admin-tabs';
    const tabContentContainer = document.createElement('div');
    tabContentContainer.className = 'tab-content-wrapper';

    tabConfig.forEach((tabInfo, tabIndex) => {
        const validContent = tabInfo.content.filter(el => el);
        if (validContent.length === 0) return;

        const tabButton = document.createElement('li');
        tabButton.textContent = tabInfo.title;
        tabButton.dataset.tabIndex = tabIndex;
        tabsContainer.appendChild(tabButton);

        const contentDiv = document.createElement('div');
        contentDiv.dataset.tabIndex = tabIndex;
        contentDiv.className = 'tab-content';
        validContent.forEach(el => contentDiv.appendChild(el));
        tabContentContainer.appendChild(contentDiv);
    });

    const firstModule = form.querySelector('.module');
    if (firstModule) {
        firstModule.parentNode.insertBefore(tabsContainer, firstModule);
        firstModule.parentNode.insertBefore(tabContentContainer, tabsContainer.nextSibling);
    }

    function activateTab(tabElement) {
        const tabIndex = tabElement.dataset.tabIndex;
        tabsContainer.querySelectorAll('li').forEach(li => li.classList.remove('active'));
        tabElement.classList.add('active');
        tabContentContainer.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('hidden', content.dataset.tabIndex !== tabIndex);
        });
    }

    const firstTabButton = tabsContainer.querySelector('li');
    if (firstTabButton) {
        activateTab(firstTabButton);
    }

    tabsContainer.addEventListener('click', (e) => {
        if (e.target.tagName === 'LI') {
            activateTab(e.target);
        }
    });
});