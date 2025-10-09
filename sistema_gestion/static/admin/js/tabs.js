// static/admin/js/articulo_tabs.js (Versión Final)
window.addEventListener('DOMContentLoaded', (event) => {
    const form = document.querySelector('#articulo_form');
    if (!form) return;

    setTimeout(() => {
        const submitRows = form.querySelectorAll('.submit-row');
        if (submitRows.length > 1) { submitRows[0].remove(); }
    }, 100);

    const allFieldsets = Array.from(form.querySelectorAll('fieldset'));
    if (allFieldsets.length < 2) return;

    const tabConfig = [
        { title: 'Información General', sections: ['Información Principal', 'Descripciones Detalladas'] },
        { title: 'Precios', sections: ['Precios y Costos'] },
        { title: 'Stock', sections: ['Stock'] }
    ];
    const tabsContainer = document.createElement('ul');
    tabsContainer.className = 'admin-tabs';
    const tabContentContainer = document.createElement('div');
    tabContentContainer.className = 'tab-content-wrapper';

    tabConfig.forEach((tabInfo, tabIndex) => {
        const contentDiv = document.createElement('div');
        contentDiv.dataset.tabIndex = tabIndex;
        contentDiv.className = 'tab-content';
        let contentFound = false;
        tabInfo.sections.forEach(sectionTitle => {
            const fieldset = allFieldsets.find(fs => {
                const h2 = fs.querySelector('h2');
                return h2 && h2.textContent.trim() === sectionTitle;
            });
            if (fieldset) {
                contentDiv.appendChild(fieldset);
                contentFound = true;
            }
        });
        if (contentFound) {
            const tabButton = document.createElement('li');
            tabButton.textContent = tabInfo.title;
            tabButton.dataset.tabIndex = tabIndex;
            tabsContainer.appendChild(tabButton);
            tabContentContainer.appendChild(contentDiv);
        }
    });

    const technicalFieldset = allFieldsets.find(fs => !fs.querySelector('h2'));
    if (technicalFieldset) { technicalFieldset.style.display = 'none'; }

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
    if (firstTabButton) { activateTab(firstTabButton); }

    tabsContainer.addEventListener('click', (e) => {
        if (e.target.tagName === 'LI') { activateTab(e.target); }
    });
});