document.addEventListener('DOMContentLoaded', function() {
    
    function generateTableColumns() {
        const grid = document.getElementById('tableColumnsGrid');
        if (!grid) return;
        grid.innerHTML = ''; 

        const headers = document.querySelectorAll('#printableArea th[data-print-field]');
        if (headers.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1 / -1; text-align: center; color: #999; font-size: 0.8rem; padding: 0.5rem;">لا توجد أعمدة قابلة للطباعة</div>';
            return;
        }
        
        headers.forEach(th => {
            const target = th.getAttribute('data-print-field');
            const clone = th.cloneNode(true);
            const sortIcon = clone.querySelector('.sort-icon');
            if(sortIcon) sortIcon.remove();
            const label = clone.textContent.trim();
            
            const labelEl = document.createElement('label');
            labelEl.className = 'field-check';
            
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.checked = true;
            input.setAttribute('data-target', target);
            
            const labelText = document.createTextNode(' ' + label + ' ');
            const keySpan = document.createElement('span');
            keySpan.className = 'field-key';
            keySpan.textContent = target.replace('col-', '');
            
            labelEl.appendChild(input);
            labelEl.appendChild(labelText);
            labelEl.appendChild(keySpan);
            grid.appendChild(labelEl);
        });
    }

    generateTableColumns();

    function getCompanySettings() {
        try {
            const scriptTag = document.getElementById('companyData');
            if (scriptTag) {
                const data = JSON.parse(scriptTag.textContent);
                if (!data.logo_url || data.logo_url === '' || data.logo_url === 'None') data.logo_url = '';
                if (data.logo_url && !data.logo_url.startsWith('/media/') && !data.logo_url.startsWith('http://') && !data.logo_url.startsWith('https://')) {
                    data.logo_url = '/media/company_logos/' + data.logo_url;
                }
                return data;
            }
        } catch (e) { console.warn('❌ خطأ في قراءة بيانات الشركة:', e); }
        return { name: 'شركة تجريبية', logo_url: '', phone: '0591234567', address: 'دمشق - سوريا', footer_text: 'شكراً لتعاملكم معنا' };
    }

    function populatePrintHeaderFooter() {
        const company = getCompanySettings();
        document.getElementById('phCompanyName').textContent = company.name;
        document.getElementById('watermarkText').textContent = company.name;
        
        let details = [];
        if (company.phone) details.push('📞 ' + company.phone);
        if (company.address) details.push('📍 ' + company.address);
        document.getElementById('phCompanyDetails').textContent = details.join(' | ');
        document.getElementById('phFooterText').textContent = company.footer_text;
        
        const img = document.getElementById('phLogoImg');
        const placeholder = document.getElementById('phLogoPlaceholder');
        const previewImg = document.getElementById('logoPreviewImg');
        const previewPlaceholder = document.getElementById('logoPreviewPlaceholder');
        
        const hasLogo = company.logo_url && company.logo_url !== '' && company.logo_url !== 'None';
        if (hasLogo) {
            img.src = company.logo_url; img.style.display = 'block'; placeholder.style.display = 'none';
            previewImg.src = company.logo_url; previewImg.style.display = 'block'; previewPlaceholder.style.display = 'none';
            img.onerror = function() { img.style.display = 'none'; placeholder.style.display = 'inline'; previewImg.style.display = 'none'; previewPlaceholder.style.display = 'inline'; };
        } else {
            img.style.display = 'none'; placeholder.style.display = 'inline'; previewImg.style.display = 'none'; previewPlaceholder.style.display = 'inline';
        }
        
        document.getElementById('companyNameInput').value = company.name;
        let detailsText = [];
        if (company.phone) detailsText.push('هاتف: ' + company.phone);
        if (company.address) detailsText.push('عنوان: ' + company.address);
        document.getElementById('companyDetailsInput').value = detailsText.join(' | ');
    }
    populatePrintHeaderFooter();

    var defaultState = { paperSize: 'a4', marginSize: 'normal', format: 'standard', logoSize: 'large', printColors: true, printLines: true, showIndex: true, showWatermark: true, notes: '' };
    var printState = { ...defaultState };
    var printModal = document.getElementById('printModal');
    var pdfExportModal = document.getElementById('pdfExportModal');
    var toastEl = document.getElementById('toast');
    var toastTimeout = null;

    function applyLogoSize(size) {
        var previewImg = document.getElementById('logoPreviewImg');
        var headerImg = document.getElementById('phLogoImg');
        if (!previewImg) return;
        if (size === 'small') { previewImg.style.maxHeight = '30px'; if (headerImg) headerImg.style.maxHeight = '20px'; }
        else if (size === 'medium') { previewImg.style.maxHeight = '45px'; if (headerImg) headerImg.style.maxHeight = '35px'; }
        else if (size === 'large') { previewImg.style.maxHeight = '65px'; if (headerImg) headerImg.style.maxHeight = '50px'; }
    }

    function showToast(msg, type, duration) {
        duration = duration || 2500; type = type || 'info';
        if (!toastEl) return;
        toastEl.textContent = msg;
        toastEl.className = 'toast toast-' + type + ' show';
        toastEl.style.display = 'block';
        if (toastTimeout) clearTimeout(toastTimeout);
        toastTimeout = setTimeout(function() { toastEl.classList.remove('show'); setTimeout(function() { toastEl.style.display = 'none'; }, 500); }, duration);
    }

    function savePrintSettings() {
        const settings = {
            paperSize: printState.paperSize, marginSize: printState.marginSize, format: printState.format, logoSize: printState.logoSize,
            printColors: document.getElementById('printColors').checked, printLines: document.getElementById('printLines').checked,
            showIndex: document.getElementById('showIndex').checked, showWatermark: document.getElementById('showWatermark').checked,
            notes: document.getElementById('printNotes').value || ''
        };
        localStorage.setItem('print_settings', JSON.stringify(settings));
        showToast('✅ تم حفظ الإعدادات بنجاح', 'success', 1500);
        closeModal('printModal');
    }

    function resetPrintSettings() {
        localStorage.removeItem('print_settings');
        printState = { ...defaultState };
        document.querySelectorAll('#paperSizeGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === 'a4'));
        document.querySelectorAll('#marginGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === 'normal'));
        document.querySelectorAll('#formatGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === 'standard'));
        document.querySelectorAll('#logoSizeGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === 'large'));
        document.querySelectorAll('#printModal input[type="checkbox"][data-target]').forEach(cb => cb.checked = true);
        document.getElementById('printColors').checked = true;
        document.getElementById('printLines').checked = true;
        document.getElementById('showIndex').checked = true;
        document.getElementById('showWatermark').checked = true;
        document.getElementById('printNotes').value = '';
        applyLogoSize('large');
        showToast('🔄 تم استعادة الإعدادات الافتراضية', 'info', 1500);
    }

    function loadPrintSettings() {
        const saved = localStorage.getItem('print_settings');
        if (saved) {
            try {
                const settings = JSON.parse(saved);
                printState.paperSize = settings.paperSize || 'a4';
                printState.marginSize = settings.marginSize || 'normal';
                printState.format = settings.format || 'standard';
                printState.logoSize = settings.logoSize || 'large';
                document.querySelectorAll('#paperSizeGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === printState.paperSize));
                document.querySelectorAll('#marginGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === printState.marginSize));
                document.querySelectorAll('#formatGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === printState.format));
                document.querySelectorAll('#logoSizeGroup .btn-opt').forEach(btn => btn.classList.toggle('active', btn.dataset.value === printState.logoSize));
                document.getElementById('printColors').checked = settings.printColors !== undefined ? settings.printColors : true;
                document.getElementById('printLines').checked = settings.printLines !== undefined ? settings.printLines : true;
                document.getElementById('showIndex').checked = settings.showIndex !== undefined ? settings.showIndex : true;
                document.getElementById('showWatermark').checked = settings.showWatermark !== undefined ? settings.showWatermark : true;
                document.getElementById('printNotes').value = settings.notes || '';
                applyLogoSize(printState.logoSize);
            } catch (e) { console.error("Error loading settings:", e); }
        } else { applyLogoSize('large'); }
    }

    function changePrintPage() {
        var existing = document.getElementById('dynamic-page-style');
        if (existing) existing.remove();
        var style = document.createElement('style');
        style.id = 'dynamic-page-style';
        var margin = '10mm', size = '';
        if (printState.marginSize === 'minimal') margin = '3mm';
        else if (printState.marginSize === 'normal') margin = '8mm';
        else if (printState.marginSize === 'wide') margin = '15mm';
        if (printState.paperSize === 'thermal') { margin = '2mm'; size = 'size: 80mm auto;'; }
        style.textContent = '@page { margin: ' + margin + '; ' + size + ' }';
        document.head.appendChild(style);
    }

    var hiddenElements = [];
    function hideBaseElements() {
        ['nav', 'aside', '.navbar', '.sidebar', 'footer', '.footer'].forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if (el.closest('.invoice-print-area') || el.closest('.modal-overlay') || el.closest('.print-fab')) return;
                hiddenElements.push({ el, display: el.style.display });
                el.style.display = 'none';
            });
        });
    }
    function showBaseElements() {
        hiddenElements.forEach(item => item.el.style.display = item.display);
        hiddenElements = [];
    }

    function closeModal(modalId) {
        var modal = document.getElementById(modalId);
        if (modal) { modal.classList.remove('active'); modal.style.display = 'none'; }
    }
    function openModal(modalId) {
        var modal = document.getElementById(modalId);
        if (modal) { modal.style.display = 'flex'; modal.classList.add('active'); }
    }

    function preparePrintSettings() {
        const company = getCompanySettings();
        document.getElementById('phCompanyName').textContent = company.name;
        let details = [];
        if (company.phone) details.push('📞 ' + company.phone);
        if (company.address) details.push('📍 ' + company.address);
        document.getElementById('phCompanyDetails').textContent = details.join(' | ');
        
        var notes = document.getElementById('printNotes').value.trim();
        var printableArea = document.getElementById('printableArea');
        
        // إنشاء أو جلب حاوية الملاحظات في آخر الصفحة (داخل منطقة الطباعة)
        var lastPageNotes = document.getElementById('lastPageNotes');
        if (!lastPageNotes) {
            lastPageNotes = document.createElement('div');
            lastPageNotes.id = 'lastPageNotes';
            lastPageNotes.className = 'print-last-page-notes';
            printableArea.appendChild(lastPageNotes);
        }
        
        // إخفاء الحاوية تماماً إذا لم يكتب المستخدم ملاحظات لمنع ظهور صفحة فارغة
        if (notes) {
            lastPageNotes.innerHTML = '<div class="notes-label">📝 ملاحظات:</div><div class="notes-content">' + notes.replace(/\n/g, '<br>') + '</div>';
            lastPageNotes.style.display = 'block';
        } else {
            lastPageNotes.innerHTML = '';
            lastPageNotes.style.display = 'none';
        }
        
        document.getElementById('phFooterText').textContent = company.footer_text;
        
        const phLogoImg = document.getElementById('phLogoImg');
        const phLogoPlaceholder = document.getElementById('phLogoPlaceholder');
        const hasLogo = company.logo_url && company.logo_url !== '' && company.logo_url !== 'None';
        if (hasLogo) {
            phLogoImg.src = company.logo_url; phLogoImg.style.display = 'block'; phLogoPlaceholder.style.display = 'none';
        } else { phLogoImg.style.display = 'none'; phLogoPlaceholder.style.display = 'inline'; }
        
        document.querySelectorAll('#printModal input[type="checkbox"][data-target]').forEach(cb => {
            printableArea.querySelectorAll('[data-print-field="' + cb.dataset.target + '"]').forEach(el => {
                el.setAttribute('data-print-hidden', cb.checked ? 'false' : 'true');
            });
        });
        
        var showIndex = document.getElementById('showIndex');
        printableArea.querySelectorAll('table thead th:first-child, table tbody td:first-child').forEach(el => {
            el.setAttribute('data-print-hidden', showIndex.checked ? 'false' : 'true');
        });
        
        printableArea.classList.toggle('print-grayscale', !document.getElementById('printColors').checked);
        printableArea.classList.toggle('print-no-lines', !document.getElementById('printLines').checked);
        printableArea.classList.remove('print-compact', 'print-detailed');
        if (printState.format === 'compact') printableArea.classList.add('print-compact');
        else if (printState.format === 'detailed') printableArea.classList.add('print-detailed');
        
        document.getElementById('printHeaderArea').classList.remove('print-logo-small', 'print-logo-medium', 'print-logo-large');
        document.getElementById('printHeaderArea').classList.add('print-logo-' + printState.logoSize);
        document.getElementById('watermarkText').style.display = document.getElementById('showWatermark').checked ? 'block' : 'none';
        changePrintPage();
    }

    function executePrint(direct) {
        var header = document.getElementById('printHeaderArea');
        var footer = document.getElementById('printFooterArea');
        var printBtn = document.getElementById('executePrintBtn');
        
        if (!direct) {
            printBtn.disabled = true;
            printBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> جاري التجهيز...';
        }
        
        preparePrintSettings();
        header.style.display = 'block'; header.classList.remove('no-print');
        footer.style.display = 'block'; footer.classList.remove('no-print');
        hideBaseElements(); 
        
        closeModal('printModal');
        closeModal('pdfExportModal');
        
        setTimeout(function() {
            window.print();
            
            // تنظيف فوري بعد إغلاق نافذة الطباعة (أو الضغط على Cancel)
            header.style.display = 'none'; header.classList.add('no-print');
            footer.style.display = 'none'; footer.classList.add('no-print');
            
            const printableArea = document.getElementById('printableArea');
            printableArea.querySelectorAll('[data-print-field]').forEach(el => el.removeAttribute('data-print-hidden'));
            printableArea.querySelectorAll('table thead th:first-child, table tbody td:first-child').forEach(el => el.removeAttribute('data-print-hidden'));
            printableArea.classList.remove('print-grayscale', 'print-no-lines', 'print-compact', 'print-detailed');
            
            document.getElementById('printHeaderArea').classList.remove('print-logo-small', 'print-logo-medium', 'print-logo-large');
            document.getElementById('watermarkText').style.display = 'none';
            
            // تفريغ الملاحظات من الحاوية المؤقتة
            var lastPageNotes = document.getElementById('lastPageNotes');
            if (lastPageNotes) {
                lastPageNotes.innerHTML = '';
                lastPageNotes.style.display = 'none';
            }
            
            showBaseElements();
            var dynStyle = document.getElementById('dynamic-page-style');
            if (dynStyle) dynStyle.remove();
            
            if (!direct) {
                printBtn.disabled = false;
                printBtn.innerHTML = '<i class="fas fa-print"></i> طباعة الآن';
            }
            showToast('✅ تم تجهيز الملف بنجاح', 'success', 2500);
        }, 300);
    }

    function executePrintDirectly() { preparePrintSettings(); executePrint(true); }

    document.getElementById('openPrintModalBtn').addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation(); openModal('printModal'); loadPrintSettings();
    });
    document.getElementById('closeModalBtn').addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation(); closeModal('printModal');
    });
    printModal.addEventListener('click', function(e) { if (e.target === printModal) closeModal('printModal'); });
    document.getElementById('closePdfModalBtn').addEventListener('click', function(e) {
        e.preventDefault(); e.stopPropagation(); closeModal('pdfExportModal');
    });
    pdfExportModal.addEventListener('click', function(e) { if (e.target === pdfExportModal) closeModal('pdfExportModal'); });
    document.getElementById('selectAllBtn').addEventListener('click', function(e) {
        e.preventDefault(); document.querySelectorAll('#printModal input[type="checkbox"][data-target]').forEach(cb => cb.checked = true); showToast('✅ تم تحديد جميع الحقول', 'success', 1500);
    });
    document.getElementById('deselectAllBtn').addEventListener('click', function(e) {
        e.preventDefault(); document.querySelectorAll('#printModal input[type="checkbox"][data-target]').forEach(cb => cb.checked = false); showToast('✅ تم إلغاء تحديد جميع الحقول', 'success', 1500);
    });
    document.getElementById('saveSettingsBtn').addEventListener('click', function(e) { e.preventDefault(); savePrintSettings(); });
    document.getElementById('resetSettingsBtn').addEventListener('click', function(e) { e.preventDefault(); resetPrintSettings(); });
    document.getElementById('exportPdfBtn').addEventListener('click', function(e) {
        e.preventDefault(); closeModal('printModal'); setTimeout(function() { openModal('pdfExportModal'); }, 300);
    });
    document.getElementById('confirmPdfExportBtn').addEventListener('click', function(e) {
        e.preventDefault(); closeModal('pdfExportModal'); setTimeout(function() { executePrintDirectly(); }, 300);
    });

    document.querySelectorAll('.btn-group-print').forEach(function(group) {
        group.querySelectorAll('.btn-opt').forEach(function(btn) {
            btn.addEventListener('click', function() {
                group.querySelectorAll('.btn-opt').forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                if (group.id === 'paperSizeGroup') printState.paperSize = this.dataset.value;
                if (group.id === 'marginGroup') printState.marginSize = this.dataset.value;
                if (group.id === 'formatGroup') printState.format = this.dataset.value;
                if (group.id === 'logoSizeGroup') { printState.logoSize = this.dataset.value; applyLogoSize(printState.logoSize); }
            });
        });
    });

    document.querySelectorAll('.toggle-switch').forEach(function(sw) {
        sw.addEventListener('click', function(e) { e.stopPropagation(); var input = this.querySelector('input'); if (input) input.checked = !input.checked; });
    });

    document.getElementById('executePrintBtn').addEventListener('click', function(e) { e.preventDefault(); executePrint(false); });
});