{% load static %}
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}نظام إدارة الفواتير{% endblock %}</title>

    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.rtl.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script nonce="{{ csp_nonce }}">
        tailwind.config = { prefix: 'tw-', corePlugins: { preflight: false } }
    </script>

    <style>
        :root {
            --aqua-1: #e0f7fa; --aqua-2: #b2ebf2; --aqua-3: #4dd0e1; --aqua-4: #0097a7;
            --text-dark: #006064; --text-light: #ffffff;
            --shadow-sm: 0 2px 8px rgba(0, 150, 167, 0.08);
            --shadow-md: 0 4px 12px rgba(0, 150, 167, 0.12);
            --sidebar-width: 280px; --navbar-height: 60px; --navbar-gutter: 0.5rem;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'Tajawal', sans-serif; background-color: var(--aqua-1);
            color: var(--text-dark); direction: rtl; text-align: right;
            min-height: 100vh; display: flex; flex-direction: column; font-size: 0.9rem;
        }

        .sidebar-toggle span { display: block; width: 18px; height: 2px; background-color: rgba(255,255,255,0.6); border-radius: 2px; transition: all 0.3s ease; }
        .sidebar-toggle:hover span { background-color: var(--text-light); }
        .sidebar-toggle.active span:nth-child(1) { transform: rotate(45deg) translate(5px, 5px); }
        .sidebar-toggle.active span:nth-child(2) { opacity: 0; }
        .sidebar-toggle.active span:nth-child(3) { transform: rotate(-45deg) translate(5px, -5px); }
        .menu-toggle-btn { gap: 3px; background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.15); }

        .navbar-mainbg { background: transparent; height: calc(var(--navbar-height) + var(--navbar-gutter)); padding-top: var(--navbar-gutter); padding-left: var(--navbar-gutter); padding-right: var(--navbar-gutter); position: fixed; top: 0; left: 0; right: 0; z-index: 1030; }
        .navbar-inner { max-width: 1400px; width: 100%; margin: 0 auto; padding: 0 1rem; height: var(--navbar-height); display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, var(--aqua-4) 0%, #006064 100%); border-radius: 12px; box-shadow: var(--shadow-md); }
        .navbar-right-section { display: flex; align-items: center; gap: 10px; flex-shrink: 0; min-width: 0; }
        .navbar-logo { display: flex; align-items: center; gap: 6px; text-decoration: none; color: var(--text-light); font-weight: 700; font-size: 0.9rem; min-width: 0; }
        .navbar-logo:hover { color: var(--text-light); }
        .logo-icon { width: 40px; height: 40px; background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.3); border-radius: 4px; display: flex; align-items: center; justify-content: center; overflow: hidden; flex-shrink: 0; }
        .logo-icon i { color: var(--text-light); font-size: 1.1rem; }
        .logo-icon img { width: 100%; height: 100%; object-fit: contain; }
        .navbar-logo .company-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex-shrink: 1; min-width: 0; }

        .navbar-center-section { flex: 1; display: flex; justify-content: flex-start; overflow: visible; margin-right: 10px; }
        #navbarSupportedContent { position: relative; overflow: visible; }
        #navbarSupportedContent ul { padding: 0; margin: 0; list-style: none; display: flex; align-items: stretch; }
        #navbarSupportedContent li { float: right; position: relative; }
        #navbarSupportedContent ul li a { color: rgba(255,255,255,0.7); text-decoration: none; font-size: 13px; font-weight: 500; display: flex; align-items: center; justify-content: center; padding: 18px 7px; position: relative; transition: color 0.3s ease; white-space: nowrap; gap: 4px; }
        #navbarSupportedContent ul li a i.nav-icon { font-size: 0.75rem; margin: 0; }
        #navbarSupportedContent>ul>li.active>a { color: var(--aqua-4); font-weight: 600; }
        #navbarSupportedContent>ul>li:hover>a { color: rgba(255,255,255,0.95); }
        #navbarSupportedContent ul li.has-submenu>a:not(:only-child):after { content: "\f107"; font-family: "Font Awesome 5 Free"; font-weight: 900; font-size: 9px; margin-right: 1px; transition: transform 0.3s ease; }
        #navbarSupportedContent>ul>li.has-submenu:hover>a:not(:only-child):after, #navbarSupportedContent>ul>li.has-submenu.active>a:not(:only-child):after { transform: rotate(180deg); }

        .hori-selector { display: inline-block; position: absolute; height: 100%; top: 0; left: 0; transition-duration: 0.6s; transition-timing-function: cubic-bezier(0.68, -0.55, 0.265, 1.55); background-color: rgba(255, 255, 255, 0.95); border-top-left-radius: 10px; border-top-right-radius: 10px; margin-top: 8px; z-index: 0; }
        #navbarSupportedContent>ul>li { z-index: 1; }

        .menu-submenu { position: absolute; top: 100%; right: 0; transform: translateY(-6px); min-width: 220px; background: white; border-radius: 0 0 12px 12px; box-shadow: var(--shadow-md); border: 1px solid var(--aqua-2); border-top: 3px solid var(--aqua-3); padding: 6px 0; opacity: 0; visibility: hidden; transition: all 0.25s ease; z-index: 1060; max-height: 80vh; overflow-y: auto; text-align: right; }
        #navbarSupportedContent li.has-submenu:hover>.menu-submenu { opacity: 1; visibility: visible; transform: translateY(0); }
        .menu-submenu li { float: none !important; }
        .menu-submenu li a { color: var(--text-dark) !important; padding: 9px 16px 9px 12px !important; font-size: 0.82rem !important; display: flex; align-items: center; gap: 10px; transition: all 0.15s ease; }
        .menu-submenu li a i { color: #9ca3af; font-size: 0.78rem; width: 18px; text-align: center; margin: 0 !important; transition: color 0.15s ease; }
        .menu-submenu li a:hover { background-color: var(--aqua-1) !important; color: var(--aqua-4) !important; }
        .menu-submenu li a:hover i { color: var(--aqua-4) !important; }
        .menu-submenu li.sub-active a { background-color: var(--aqua-1) !important; color: var(--aqua-4) !important; font-weight: 600; }
        .menu-submenu li.sub-active a i { color: var(--aqua-4) !important; }
        .menu-submenu li a.pos-quick-link { color: #047857 !important; font-weight: 700 !important; }
        .menu-submenu li a.pos-quick-link i { color: #047857 !important; }
        .menu-submenu li a.pos-quick-link:hover { background-color: #d1fae5 !important; color: #065f46 !important; }
        .menu-submenu li a.pos-quick-link:hover i { color: #065f46 !important; }
        .submenu-cart-badge { background: #00897b; color: white; font-size: 0.6rem; padding: 1px 6px; border-radius: 4px; margin-right: auto; font-weight: 700; }

        .reports-submenu { display: grid !important; grid-template-columns: repeat(2, minmax(200px, 1fr)); min-width: 440px !important; max-width: 500px !important; padding: 0 !important; }
        .reports-submenu li { break-inside: avoid; }
        .reports-submenu li a { border-radius: 0 !important; padding: 10px 14px !important; }
        #navbarSupportedContent li.has-submenu:last-child .reports-submenu { border-radius: 0 0 12px 12px; }

        .navbar-left-section { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
        .nav-username { color: rgba(255,255,255,0.9); font-size: 0.82rem; font-weight: 600; max-width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .nav-action-btn { position: relative; width: 34px; height: 34px; border-radius: 4px; display: flex; align-items: center; justify-content: center; background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.75); border: 1px solid rgba(255,255,255,0.15); cursor: pointer; transition: all 0.2s ease; text-decoration: none; font-size: 0.88rem; }
        .nav-action-btn:hover { background: rgba(255,255,255,0.2); color: var(--text-light); border-color: rgba(255,255,255,0.3); }
        .nav-badge { position: absolute; top: -4px; left: -4px; min-width: 16px; height: 16px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 0.55rem; font-weight: 700; padding: 0 3px; border: 2px solid var(--aqua-4); }
        .nav-badge.green { background: #00897b; color: white; }
        .nav-badge.red { background: #e53935; color: white; animation: badgePulse 2s infinite; }
        @keyframes badgePulse { 0% { box-shadow: 0 0 0 0 rgba(229,57,53,0.5); } 70% { box-shadow: 0 0 0 6px rgba(229,57,53,0); } 100% { box-shadow: 0 0 0 0 rgba(229,57,53,0); } }

        .user-dropdown { position: relative; }
        .user-dropdown-trigger { display: flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 4px; border: 2px solid rgba(255,255,255,0.4); background: rgba(255,255,255,0.15); cursor: pointer; overflow: hidden; transition: all 0.2s ease; }
        .user-dropdown-trigger:hover { border-color: rgba(255,255,255,0.7); background: rgba(255,255,255,0.25); }
        .user-dropdown-trigger img { width: 100%; height: 100%; object-fit: cover; }
        .user-dropdown-trigger i { color: rgba(255,255,255,0.7); font-size: 0.75rem; }

        .user-dropdown-backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); z-index: 10750; opacity: 0; visibility: hidden; pointer-events: none; transition: opacity 0.25s ease, visibility 0.25s ease; }
        .user-dropdown-backdrop.active { opacity: 1; visibility: visible; pointer-events: auto; }

        .user-dropdown-menu { position: fixed; min-width: 230px; background: #ffffff; border-radius: 12px; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.15); border: 1px solid var(--aqua-2); padding: 0; z-index: 10760; overflow: hidden; opacity: 0; visibility: hidden; pointer-events: none; transform: scale(0.95); transform-origin: top center; transition: opacity 0.2s ease, visibility 0.2s ease, transform 0.2s ease; }
        .user-dropdown-menu.show { opacity: 1; visibility: visible; pointer-events: auto; transform: scale(1); }
        .user-dropdown-menu .ud-header { padding: 12px 16px; background: linear-gradient(135deg, var(--aqua-4) 0%, #006064 100%); color: var(--text-light); }
        .user-dropdown-menu .ud-name { font-size: 0.88rem; font-weight: 600; margin: 0; }
        .user-dropdown-menu .ud-role { font-size: 0.72rem; opacity: 0.8; margin: 2px 0 0; }
        .user-dropdown-menu .ud-login-info { padding: 8px 16px; background: var(--aqua-1); display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--text-dark); border-bottom: 1px solid var(--aqua-2); }
        .user-dropdown-menu .ud-login-info i { color: var(--aqua-4); font-size: 0.7rem; }
        .user-dropdown-menu .ud-login-info span { opacity: 0.75; }
        .user-dropdown-menu .ud-links { padding: 6px 0; }
        .user-dropdown-menu a, .user-dropdown-menu button { display: flex; align-items: center; gap: 10px; width: 100%; padding: 9px 16px; font-size: 0.82rem; color: var(--text-dark); text-decoration: none; background: none; border: none; cursor: pointer; transition: all 0.15s ease; font-family: 'Tajawal', sans-serif; text-align: right; }
        .user-dropdown-menu a:hover, .user-dropdown-menu button:hover { background: var(--aqua-1); color: var(--aqua-4); }
        .user-dropdown-menu a i, .user-dropdown-menu button i { color: #9ca3af; width: 16px; text-align: center; transition: color 0.15s ease; }
        .user-dropdown-menu a:hover i, .user-dropdown-menu button:hover i { color: var(--aqua-4); }
        .user-dropdown-menu hr { margin: 0; border-color: var(--aqua-2); }
        .ud-logout { color: #e53935; }

        @media (max-width: 768px) {
            .user-dropdown-menu { top: auto !important; bottom: 0 !important; left: 0 !important; right: 0 !important; width: 100% !important; max-width: 100% !important; min-width: 100% !important; border-radius: 20px 20px 0 0 !important; border: none !important; border-top: 3px solid var(--aqua-3) !important; box-shadow: 0 -4px 30px rgba(0, 0, 0, 0.15) !important; max-height: 85vh; overflow-y: auto; transform: translateY(100%) !important; transform-origin: bottom center !important; transition: transform 0.3s cubic-bezier(0.32, 0.72, 0, 1), opacity 0.3s ease, visibility 0.3s ease !important; }
            .user-dropdown-menu.show { transform: translateY(0) !important; }
            .user-dropdown-menu::before { content: ''; display: block; width: 36px; height: 4px; background: #d0d0d0; border-radius: 4px; margin: 10px auto 0; }
            .user-dropdown-menu .ud-header { padding: 14px 20px 12px; }
            .user-dropdown-menu .ud-name { font-size: 0.95rem; }
            .user-dropdown-menu .ud-role { font-size: 0.78rem; }
            .user-dropdown-menu .ud-login-info { padding: 10px 20px; font-size: 0.75rem; }
            .user-dropdown-menu .ud-links { padding: 8px 0 16px; }
            .user-dropdown-menu a, .user-dropdown-menu button { padding: 13px 20px; font-size: 0.92rem; gap: 12px; }
            .user-dropdown-menu a i, .user-dropdown-menu button i { width: 22px; font-size: 0.9rem; }
            .user-dropdown-menu hr { margin: 4px 0; }
        }

        .sidebar { position: fixed; top: calc(var(--navbar-height) + var(--navbar-gutter)); right: 0; width: var(--sidebar-width); height: calc(100vh - var(--navbar-height) - var(--navbar-gutter)); background-color: white; box-shadow: -2px 0 15px rgba(0, 150, 167, 0.08); z-index: 1020; transition: right 0.3s ease, width 0.3s ease; overflow-y: auto; overflow-x: hidden; transform: translateX(100%); right: 0; }
        .sidebar.active { transform: translateX(0); }

        .sidebar-login-bar { padding: 10px 16px; background: var(--aqua-1); border-bottom: 1px solid var(--aqua-2); display: flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--text-dark); flex-shrink: 0; }
        .sidebar-login-bar i { color: var(--aqua-4); font-size: 0.7rem; }
        .sidebar-login-bar .sl-label { opacity: 0.6; }
        .sidebar-login-bar .sl-value { font-weight: 600; }

        .sidebar-menu { list-style: none; padding: 8px 0; margin: 0; }
        .sidebar-item { position: relative; }
        .sidebar-link { display: flex; align-items: center; padding: 11px 18px; color: var(--text-dark); text-decoration: none; transition: all 0.2s ease; font-weight: 500; font-size: 0.85rem; position: relative; }
        .sidebar-link:hover { background-color: var(--aqua-1); color: var(--aqua-4); }
        .sidebar-link.active { background-color: var(--aqua-1); color: var(--aqua-4); font-weight: 600; }
        .sidebar-link.active::before { content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 3px; background: linear-gradient(180deg, var(--aqua-3), var(--aqua-4)); border-radius: 0 3px 3px 0; }
        .sidebar-icon { font-size: 0.95rem; width: 22px; text-align: center; margin-left: 10px; flex-shrink: 0; }
        .sidebar-text { white-space: nowrap; }
        .sidebar-arrow { margin-right: auto; transition: transform 0.3s ease; font-size: 0.65rem; color: #9ca3af; flex-shrink: 0; }
        .sidebar-item.has-dropdown.active .sidebar-arrow { transform: rotate(180deg); color: var(--aqua-4); }
        .sidebar-dropdown { list-style: none; padding: 0; margin: 0; max-height: 0; overflow: hidden; transition: max-height 0.35s ease; background-color: rgba(224, 247, 250, 0.3); }
        .sidebar-item.has-dropdown.active .sidebar-dropdown { max-height: 2000px; }
        .sidebar-dropdown .sidebar-link { padding-right: 50px; font-size: 0.8rem; }
        .sidebar-cart-count { background: #00897b; color: white; font-size: 0.65rem; padding: 2px 7px; border-radius: 4px; margin-right: auto; font-weight: 700; }
        .sidebar-link.pos-quick-link { color: #047857; font-weight: 700; }
        .sidebar-link.pos-quick-link .sidebar-icon { color: #047857; }
        .sidebar-link.pos-quick-link:hover { background-color: #d1fae5; color: #065f46; }
        .sidebar-link.pos-quick-link:hover .sidebar-icon { color: #065f46; }

        .sidebar-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(0, 96, 100, 0.3); z-index: 1015; display: none; opacity: 0; transition: opacity 0.3s ease; }
        .sidebar-overlay.active { display: block; opacity: 1; }

        .main-content { max-width: 1400px; width: 100%; margin: 0 auto; padding: 0.75rem 0.5rem; padding-top: calc(var(--navbar-height) + var(--navbar-gutter) + 0.75rem); min-height: calc(100vh - var(--navbar-height) - var(--navbar-gutter)); }
        .auth-main-content { padding-top: 2rem; }

        .footer { background: transparent; color: var(--text-light); padding: 0.5rem; width: 100%; }
        .footer-container { max-width: 1400px; width: 100%; margin: 0 auto; background: linear-gradient(135deg, var(--aqua-4) 0%, #006064 100%); border-radius: 12px; padding: 1rem; box-shadow: var(--shadow-md); overflow: hidden; }
        .footer-logo { display: flex; align-items: center; gap: 0.8rem; margin-bottom: 0.8rem; }
        .footer-logo .f-logo { width: 45px; height: 45px; background: rgba(255,255,255,0.2); border-radius: 4px; display: flex; align-items: center; justify-content: center; overflow: hidden; border: 1px solid rgba(255,255,255,0.3); flex-shrink: 0; }
        .footer-logo .f-logo img { width: 100%; height: 100%; object-fit: contain; }
        .footer-logo .f-logo i { font-size: 1.2rem; }
        .footer-logo-text { font-size: 1rem; font-weight: 700; }
        .footer-links h6 { color: var(--aqua-2); margin-bottom: 0.6rem; font-weight: 600; font-size: 0.82rem; }
        .footer-links ul { list-style: none; padding: 0; }
        .footer-links li { margin-bottom: 0.2rem; }
        .footer-links a { color: rgba(255,255,255,0.65); text-decoration: none; transition: all 0.2s ease; display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; }
        .footer-links a:hover { color: var(--text-light); }
        .footer-contact i { width: 18px; color: var(--aqua-3); font-size: 0.75rem; }
        .footer-bottom { border-top: 1px solid rgba(255,255,255,0.15); padding-top: 0.8rem; margin-top: 0.8rem; text-align: center; color: rgba(255,255,255,0.5); font-size: 0.72rem; }
        .footer-copyright-left { text-align: left; }
        .social-links { display: flex; gap: 0.4rem; margin-top: 0.6rem; }
        .social-links a { width: 28px; height: 28px; border-radius: 4px; background: rgba(255,255,255,0.1); display: flex; align-items: center; justify-content: center; transition: all 0.2s ease; color: rgba(255,255,255,0.7); }
        .social-links a:hover { background: rgba(255,255,255,0.2); color: white; }

        .card { border: none; border-radius: 12px; box-shadow: var(--shadow-sm); margin-bottom: 1rem; overflow: hidden; }
        .card:hover { box-shadow: var(--shadow-md); }
        .card-header { background: linear-gradient(135deg, var(--aqua-4) 0%, #006064 100%); color: var(--text-light); padding: 0.6rem 1rem; font-weight: 600; font-size: 0.9rem; display: flex; align-items: center; gap: 0.5rem; }
        .card-body { padding: 1rem; }

        .btn { border-radius: 4px; padding: 0.35rem 0.7rem; font-weight: 600; font-size: 0.8rem; border: none; transition: all 0.2s; display: inline-flex; align-items: center; gap: 0.3rem; }
        .btn-primary { background: linear-gradient(135deg, var(--aqua-4) 0%, #006064 100%); color: white; }
        .btn-primary:hover { background: linear-gradient(135deg, #00838f 0%, #004d40 100%); transform: translateY(-1px); }
        .btn-success { background: linear-gradient(135deg, #00897b 0%, #00695c 100%); color: white; }
        .btn-success:hover { transform: translateY(-1px); }
        .btn-danger { background: linear-gradient(135deg, #e53935 0%, #b71c1c 100%); color: white; }
        .btn-danger:hover { transform: translateY(-1px); }
        .btn-warning { background: linear-gradient(135deg, #ffb300 0%, #ff8f00 100%); color: white; }
        .btn-warning:hover { transform: translateY(-1px); }

        .table { font-size: 0.8rem; }
        .table thead th { background: linear-gradient(135deg, var(--aqua-3) 0%, var(--aqua-4) 100%); color: white; font-weight: 600; text-align: center; border-color: var(--aqua-4); }

        .form-control, .form-select { border-radius: 4px; border: 1px solid var(--aqua-2); padding: 0.35rem 0.5rem; font-size: 0.8rem; transition: all 0.2s; }
        .form-control:focus, .form-select:focus { border-color: var(--aqua-3); box-shadow: 0 0 0 2px rgba(77, 208, 225, 0.2); }
        .form-label { font-weight: 500; font-size: 0.75rem; margin-bottom: 0.2rem; color: var(--text-dark); display: flex; align-items: center; gap: 0.3rem; }

        .alert { border-radius: 4px; border: none; padding: 0.6rem 1rem; margin-bottom: 1rem; font-size: 0.85rem; }
        .required-field::after { content: " *"; color: #d32f2f; }

        .stat-card { background: white; border-radius: 12px; padding: 1rem; box-shadow: var(--shadow-sm); transition: all 0.2s ease; height: 100%; }
        .stat-card:hover { transform: translateY(-3px); box-shadow: var(--shadow-md); }
        .stat-icon { width: 48px; height: 48px; border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 10px; font-size: 1.2rem; color: white; }
        .stat-icon.primary { background: linear-gradient(135deg, var(--aqua-3), var(--aqua-4)); }
        .stat-icon.success { background: linear-gradient(135deg, #00897b, #00695c); }
        .stat-icon.warning { background: linear-gradient(135deg, #ffb300, #ff8f00); }
        .stat-icon.danger { background: linear-gradient(135deg, #e53935, #b71c1c); }
        .stat-icon.info { background: linear-gradient(135deg, #8e24aa, #6a1b9a); }
        .stat-value { font-size: 1.6rem; font-weight: 700; margin-bottom: 2px; }
        .stat-label { color: #78909c; font-size: 0.8rem; }

        .wa-float-container { position: fixed; bottom: 15px; left: 15px; z-index: 99999; display: flex; align-items: center; gap: 6px; animation: wa-fadeIn 0.5s ease-out forwards; }
        .wa-float-msg { background: white; color: #333; padding: 5px 9px; border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-family: 'Tajawal', sans-serif; font-size: 11px; font-weight: 600; white-space: nowrap; opacity: 0; transform: translateX(-20px); animation: wa-slideIn 0.5s 0.3s ease-out forwards; border: 1px solid #f0f0f0; }
        .wa-float-btn { width: 30px; height: 30px; background-color: #25D366; color: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 10px rgba(37, 211, 102, 0.4); text-decoration: none !important; transition: all 0.3s ease; animation: wa-pulse 2s infinite; border: none; }
        .wa-float-btn:hover { background-color: #128C7E; transform: scale(1.1); box-shadow: 0 4px 15px rgba(37, 211, 102, 0.6); text-decoration: none !important; color: white !important; }
        .wa-float-btn svg { width: 17px; height: 17px; fill: white; }
        .wa-float-msg-hide { opacity: 0 !important; transition: opacity 0.5s ease; }
        @keyframes wa-slideIn { to { opacity: 1; transform: translateX(0); } }
        @keyframes wa-fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes wa-pulse { 0% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0.6); } 70% { box-shadow: 0 0 0 10px rgba(37, 211, 102, 0); } 100% { box-shadow: 0 0 0 0 rgba(37, 211, 102, 0); } }

        @media (min-width: 1401px) { .navbar-inner { padding: 0 1.5rem; } }
        @media (max-width: 1400px) { #navbarSupportedContent ul li a { padding: 18px 6px; font-size: 12.5px; } }
        @media (max-width: 1200px) { #navbarSupportedContent ul li a { padding: 18px 5px; font-size: 12px; } #navbarSupportedContent ul li a i.nav-icon { display: none; } .reports-submenu { display: block !important; min-width: 200px !important; max-width: unset !important; } }
        @media (max-width: 992px) { .navbar-center-section { display: none !important; } .sidebar { width: 300px; max-width: 85vw; } }
        @media (max-width: 768px) { :root { --navbar-height: 56px; --navbar-gutter: 0.25rem; } .main-content { padding: 0.5rem; padding-top: calc(var(--navbar-height) + var(--navbar-gutter) + 0.5rem); } .navbar-inner { padding: 0 0.75rem; } .navbar-right-section { gap: 8px; } .navbar-logo .company-name { font-size: 0.72rem; max-width: 130px; line-height: 1.2; } .logo-icon { width: 38px; height: 38px; } .logo-icon i { font-size: 1rem; } .nav-username { display: none !important; } .sidebar { width: 88vw; max-width: 340px; } .sidebar-login-bar { padding: 8px 14px; font-size: 0.68rem; } .sidebar-link { padding: 10px 14px; font-size: 0.82rem; } .sidebar-icon { width: 20px; font-size: 0.88rem; margin-left: 8px; } .sidebar-dropdown .sidebar-link { padding-right: 44px; font-size: 0.78rem; } .sidebar-cart-count { font-size: 0.6rem; padding: 1px 5px; } .footer { padding: 0.25rem; } .footer-container { padding: 0.75rem; } .footer-logo { flex-direction: column; text-align: center; gap: 0.4rem; } .footer-logo-text { font-size: 0.9rem; } .footer-bottom { font-size: 0.65rem; } .footer-bottom .row { flex-direction: column; gap: 0.3rem; } .footer-bottom .col-md-6 { text-align: center !important; } .card-header { padding: 0.5rem 0.8rem; font-size: 0.82rem; } .card-body { padding: 0.8rem; } .btn { font-size: 0.75rem; padding: 0.3rem 0.6rem; } .table { font-size: 0.75rem; } .form-control, .form-select { font-size: 0.78rem; } .stat-card { padding: 0.8rem; } .stat-icon { width: 40px; height: 40px; font-size: 1rem; } .stat-value { font-size: 1.3rem; } }
        @media (max-width: 576px) { :root { --navbar-gutter: 0.5rem; } .main-content { padding: 0.5rem; padding-top: calc(var(--navbar-height) + var(--navbar-gutter) + 0.5rem); } .navbar-inner { padding: 0 0.65rem; border-radius: 10px; } .navbar-logo .company-name { font-size: 0.68rem; max-width: 100px; } .navbar-right-section { gap: 6px; } .nav-action-btn { width: 30px; height: 30px; font-size: 0.8rem; } .nav-badge { min-width: 14px; height: 14px; font-size: 0.5rem; top: -3px; left: -3px; } .user-dropdown-trigger { width: 30px; height: 30px; } .sidebar { width: 92vw; max-width: none; } .sidebar-link { padding: 9px 12px; font-size: 0.8rem; } .sidebar-icon { width: 18px; font-size: 0.82rem; margin-left: 6px; } .sidebar-dropdown .sidebar-link { padding-right: 38px; font-size: 0.75rem; } .footer { padding: 0.5rem; } .footer-container { padding: 0.5rem; } .footer-links h6 { font-size: 0.72rem; margin-bottom: 0.4rem; } .footer-links a { font-size: 0.7rem; gap: 0.2rem; } .footer-contact a { font-size: 0.65rem; } .footer-contact i { width: 14px; font-size: 0.65rem; } .wa-float-msg { display: none; } .card { margin-bottom: 0.6rem; border-radius: 10px; } .card-header { padding: 0.45rem 0.6rem; font-size: 0.78rem; gap: 0.3rem; } .card-body { padding: 0.6rem; } .btn { font-size: 0.7rem; padding: 0.25rem 0.5rem; border-radius: 3px; } .table { font-size: 0.7rem; } .table thead th { font-size: 0.7rem; padding: 0.4rem 0.3rem; } .table td { padding: 0.35rem 0.3rem; } .form-control, .form-select { font-size: 0.75rem; padding: 0.3rem 0.4rem; } .form-label { font-size: 0.7rem; } .alert { font-size: 0.78rem; padding: 0.5rem 0.7rem; } .stat-card { padding: 0.6rem; border-radius: 10px; } .stat-icon { width: 36px; height: 36px; font-size: 0.9rem; margin-bottom: 6px; } .stat-value { font-size: 1.15rem; } .stat-label { font-size: 0.7rem; } .table-responsive { margin: 0 -0.5rem; } .card .table-responsive { margin: -0.6rem; border-radius: 0 0 10px 10px; overflow: hidden; } }
        @media (max-width: 400px) { :root { --navbar-height: 52px; --navbar-gutter: 0.375rem; } .navbar-inner { padding: 0 0.5rem; border-radius: 8px; } .navbar-right-section { gap: 4px; } .navbar-logo .company-name { font-size: 0.62rem; max-width: 75px; } .navbar-logo { gap: 6px; } .logo-icon { width: 34px; height: 34px; border-radius: 3px; } .logo-icon i { font-size: 0.85rem; } .sidebar-toggle span { width: 14px; } .main-content { padding: 0.375rem; padding-top: calc(var(--navbar-height) + var(--navbar-gutter) + 0.375rem); } .sidebar-link { padding: 8px 10px; font-size: 0.78rem; } .sidebar-icon { width: 16px; font-size: 0.78rem; margin-left: 5px; } .sidebar-dropdown .sidebar-link { padding-right: 32px; font-size: 0.72rem; } .sidebar-arrow { font-size: 0.55rem; } .sidebar-cart-count { font-size: 0.55rem; padding: 1px 4px; } .card { margin-bottom: 0.5rem; border-radius: 8px; } .card-header { font-size: 0.72rem; padding: 0.4rem 0.5rem; } .card-body { padding: 0.5rem; } .btn { font-size: 0.65rem; padding: 0.2rem 0.4rem; } .table { font-size: 0.65rem; } .table thead th { font-size: 0.65rem; } .stat-card { padding: 0.5rem; border-radius: 8px; } .stat-icon { width: 32px; height: 32px; font-size: 0.8rem; } .stat-value { font-size: 1rem; } .stat-label { font-size: 0.65rem; } .footer { padding: 0.375rem; } .footer-container { padding: 0.5rem; } .footer-bottom { font-size: 0.6rem; } }
    </style>

    {% block extra_css %}{% endblock %}
</head>
<body>
    {% if user.is_authenticated %}

    <nav class="navbar-mainbg">
        <div class="navbar-inner">
            <div class="navbar-right-section">
                <button type="button" id="menuToggle" class="sidebar-toggle menu-toggle-btn tw-relative tw-inline-flex tw-items-center tw-justify-center tw-rounded tw-p-2 tw-cursor-pointer tw-border-0" aria-label="القائمة">
                    <span></span><span></span><span></span>
                </button>
                <a href="{% url 'index' %}" class="navbar-logo" title="{{ company_settings.company_name|default:'نظام إدارة الفواتير' }}">
                    <div class="logo-icon">
                        {% if company_settings and company_settings.company_logo %}
                            <img src="{{ company_settings.company_logo.url }}" alt="شعار الشركة" loading="lazy">
                        {% elif company_logo %}
                            <img src="{{ company_logo.url }}" alt="شعار الشركة" loading="lazy">
                        {% else %}
                            <i class="fas fa-file-invoice-dollar"></i>
                        {% endif %}
                    </div>
                    <span class="company-name">{{ company_settings.company_name|default:"أدخل اسم شركتك" }}</span>
                </a>
            </div>

            <div class="navbar-center-section">
                <div id="navbarSupportedContent">
                    <div class="hori-selector"></div>
                    <ul>
                        <li class="has-submenu {% if 'purch' in current_url_name or 'sale' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-file-invoice nav-icon"></i>الفواتير</a>
                            <ul class="menu-submenu reports-submenu">
                                {% if perms.invoice.add_purch %}
                                <li class="{% if current_url_name == 'purch_create' %}sub-active{% endif %}"><a href="{% url 'invoice:purch_create' %}"><i class="fas fa-plus-circle"></i>إنشاء فاتورة شراء</a></li>
                                {% endif %}
                                {% if perms.invoice.view_purch %}
                                <li class="{% if current_url_name == 'purch_list' %}sub-active{% endif %}"><a href="{% url 'invoice:purch_list' %}"><i class="fas fa-list"></i>قائمة فواتير المشتريات</a></li>
                                {% endif %}
                                {% if perms.invoice.add_sale %}
                                <li class="{% if current_url_name == 'sale_create' %}sub-active{% endif %}"><a href="{% url 'invoice:sale_create' %}"><i class="fas fa-plus-circle"></i>إنشاء فاتورة بيع</a></li>
                                <li class="{% if current_url_name == 'pos_sale_create' %}sub-active{% endif %}"><a href="{% url 'invoice:pos_sale_create' %}" class="pos-quick-link"><i class="fas fa-cash-register"></i>نقطة بيع سريعة (F4)</a></li>
                                {% endif %}
                                {% if perms.invoice.view_sale %}
                                <li class="{% if current_url_name == 'sale_list' %}sub-active{% endif %}"><a href="{% url 'invoice:sale_list' %}"><i class="fas fa-list"></i>قائمة فواتير المبيعات</a></li>
                                {% endif %}
                                {% if perms.invoice.view_purchreturn %}
                                <li class="{% if current_url_name == 'purchase_return_list' %}sub-active{% endif %}"><a href="{% url 'invoice:purchase_return_list' %}"><i class="fas fa-undo"></i>مرتجعات المشتريات</a></li>
                                {% endif %}
                                {% if perms.invoice.view_salereturn %}
                                <li class="{% if current_url_name == 'sale_return_list' %}sub-active{% endif %}"><a href="{% url 'invoice:sale_return_list' %}"><i class="fas fa-receipt"></i>مرتجعات المبيعات</a></li>
                                {% endif %}
                            </ul>
                        </li>

                        {% if perms.invoice.view_product %}
                        <li class="has-submenu {% if 'product' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-boxes nav-icon"></i>المنتجات</a>
                            <ul class="menu-submenu">
                                <li class="{% if current_url_name == 'product_list' %}sub-active{% endif %}"><a href="{% url 'invoice:product_list' %}"><i class="fas fa-list"></i>قائمة المنتجات</a></li>
                                {% if perms.invoice.add_product %}
                                <li class="{% if current_url_name == 'product_create' %}sub-active{% endif %}"><a href="{% url 'invoice:product_create' %}"><i class="fas fa-plus-circle"></i>إضافة منتج</a></li>
                                {% endif %}
                                <li><a href="{% url 'invoice:barcode_statement' %}#barcode-section"><i class="fas fa-barcode"></i>إدارة الباركود</a></li>
                                {% if perms.invoice.change_product %}
                                <li class="{% if current_url_name == 'product_bulk_update' %}sub-active{% endif %}"><a href="{% url 'invoice:product_bulk_update' %}"><i class="fas fa-tags"></i>نظام التسعير</a></li>
                                {% endif %}
                            </ul>
                        </li>
                        {% endif %}

                        <li class="has-submenu {% if 'orders' in current_url_name or 'store' in current_url_name or 'checkout' in current_url_name or 'notification' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-store nav-icon"></i>المتجر الإلكتروني</a>
                            <ul class="menu-submenu">
                                {% if perms.invoice.view_order %}
                                <li class="{% if current_url_name == 'orders_list' %}sub-active{% endif %}"><a href="{% url 'invoice:orders_list' %}"><i class="fas fa-inbox"></i>إدارة الطلبات</a></li>
                                <li class="{% if current_url_name == 'admin_stock_notifications' %}sub-active{% endif %}"><a href="{% url 'invoice:admin_stock_notifications' %}"><i class="fas fa-bell"></i>تنبيهات المخزون</a></li>
                                <li class="{% if current_url_name == 'notification_archive' %}sub-active{% endif %}"><a href="{% url 'invoice:notification_archive' %}"><i class="fas fa-history"></i>أرشيف الإشعارات</a></li>
                                {% endif %}
                                {% if perms.invoice.change_order %}
                                <li class="{% if current_url_name == 'control_store' %}sub-active{% endif %}"><a href="{% url 'invoice:control_store' %}"><i class="fas fa-sliders-h"></i>إدارة المتجر</a></li>
                                {% endif %}
                                <li class="{% if current_url_name == 'store_front' %}sub-active{% endif %}"><a href="{% url 'invoice:store_front' %}" target="_blank" rel="nofollow noopener noreferrer"><i class="fas fa-external-link-alt"></i>واجهة المتجر</a></li>
                                {% if perms.invoice.view_order %}
                                <li class="{% if current_url_name == 'checkout' %}sub-active{% endif %}"><a href="{% url 'invoice:checkout' %}"><i class="fas fa-credit-card"></i>صفحة الدفع</a></li>
                                {% endif %}
                                <li>
                                    <a href="{% url 'invoice:cart_detail' %}">
                                        <i class="fas fa-shopping-cart"></i>سلة التسوق
                                        {% if cart_count > 0 %}
                                        <span class="submenu-cart-badge">{{ cart_count }}</span>
                                        {% endif %}
                                    </a>
                                </li>
                            </ul>
                        </li>

                        {% if perms.invoice.view_cashtransaction %}
                        <li class="has-submenu {% if 'cash' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-wallet nav-icon"></i>الصندوق</a>
                            <ul class="menu-submenu">
                                <li class="{% if current_url_name == 'cash_transaction_list' %}sub-active{% endif %}"><a href="{% url 'invoice:cash_transaction_list' %}"><i class="fas fa-exchange-alt"></i>حركة الصندوق</a></li>
                                {% if perms.invoice.add_cashtransaction %}
                                <li class="{% if current_url_name == 'cash_transaction_create' %}sub-active{% endif %}"><a href="{% url 'invoice:cash_transaction_create' %}"><i class="fas fa-hand-holding-usd"></i>حركة مالية</a></li>
                                {% endif %}
                            </ul>
                        </li>
                        {% endif %}

                        {% if request.user.is_superuser %}
                        <li class="has-submenu {% if 'report' in current_url_name or 'statement' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-chart-bar nav-icon"></i>التقارير</a>
                            <ul class="menu-submenu reports-submenu">
                                <li class="{% if current_url_name == 'profit_report' %}sub-active{% endif %}"><a href="{% url 'invoice:profit_report' %}"><i class="fas fa-chart-line"></i>تقرير الأرباح</a></li>
                                <li class="{% if current_url_name == 'daily_sales_summary' %}sub-active{% endif %}"><a href="{% url 'invoice:daily_sales_summary' %}"><i class="fas fa-calendar-day"></i>ملخص المبيعات اليومي</a></li>
                                <li class="{% if current_url_name == 'sales_by_customer_report' %}sub-active{% endif %}"><a href="{% url 'invoice:sales_by_customer_report' %}"><i class="fas fa-users"></i>مبيعات العملاء</a></li>
                                <li class="{% if current_url_name == 'purchases_by_supplier_report' %}sub-active{% endif %}"><a href="{% url 'invoice:purchases_by_supplier_report' %}"><i class="fas fa-truck"></i>مشتريات الموردين</a></li>
                                <li class="{% if current_url_name == 'unpaid_invoices_report' %}sub-active{% endif %}"><a href="{% url 'invoice:unpaid_invoices_report' %}"><i class="fas fa-file-invoice-dollar"></i>فواتير غير مسددة</a></li>
                                <li class="{% if current_url_name == 'unpaid_sales_report' %}sub-active{% endif %}"><a href="{% url 'invoice:unpaid_sales_report' %}"><i class="fas fa-exclamation-triangle"></i>الديون المتراكمة</a></li>
                                <li class="{% if current_url_name == 'dead_stock_report' %}sub-active{% endif %}"><a href="{% url 'invoice:dead_stock_report' %}"><i class="fas fa-box-open"></i>منتجات راكدة</a></li>
                                <li class="{% if current_url_name == 'barcode_statement' %}sub-active{% endif %}"><a href="{% url 'invoice:barcode_statement' %}"><i class="fas fa-barcode"></i>حركة الباركود</a></li>
                                <li class="{% if current_url_name == 'statement_report' %}sub-active{% endif %}"><a href="{% url 'invoice:statement_report' %}"><i class="fas fa-file-alt"></i>كشف حساب</a></li>
                            </ul>
                        </li>
                        {% endif %}

                        {% if perms.auth.view_user %}
                        <li class="has-submenu {% if 'user' in current_url_name or 'register' in current_url_name or 'permissions' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-users-cog nav-icon"></i>المستخدمين</a>
                            <ul class="menu-submenu">
                                <li class="{% if current_url_name == 'user_list' %}sub-active{% endif %}"><a href="{% url 'accounts:user_list' %}"><i class="fas fa-list"></i>قائمة المستخدمين</a></li>
                                {% if perms.auth.add_user %}
                                <li class="{% if current_url_name == 'register' %}sub-active{% endif %}"><a href="{% url 'accounts:register' %}"><i class="fas fa-user-plus"></i>إضافة مستخدم جديد</a></li>
                                {% endif %}
                                {% if request.user.is_superuser %}
                                <li class="{% if current_url_name == 'permissions' %}sub-active{% endif %}"><a href="{% url 'accounts:permissions' %}"><i class="fas fa-user-shield"></i>الصلاحيات والأدوار</a></li>
                                {% endif %}
                            </ul>
                        </li>
                        {% endif %}

                        {% if request.user.is_superuser %}
                        <li class="has-submenu {% if 'currency' in current_url_name or 'payment_method' in current_url_name or 'shipping_company' in current_url_name or 'status' in current_url_name or 'price_type' in current_url_name or 'email_settings' in current_url_name %}active{% endif %}">
                            <a href="#"><i class="fas fa-cogs nav-icon"></i>الإعدادات</a>
                            <ul class="menu-submenu">
                                <li class="{% if current_url_name == 'email_settings' %}sub-active{% endif %}"><a href="{% url 'invoice:email_settings' %}"><i class="fas fa-envelope-open-text"></i>إعدادات البريد</a></li>
                                <li class="{% if current_url_name == 'currency_list' %}sub-active{% endif %}"><a href="{% url 'invoice:currency_list' %}"><i class="fas fa-dollar-sign"></i>العملات</a></li>
                                <li class="{% if current_url_name == 'payment_method_list' %}sub-active{% endif %}"><a href="{% url 'invoice:payment_method_list' %}"><i class="fas fa-credit-card"></i>طرق الدفع</a></li>
                                <li class="{% if current_url_name == 'shipping_company_list' %}sub-active{% endif %}"><a href="{% url 'invoice:shipping_company_list' %}"><i class="fas fa-truck"></i>شركات الشحن</a></li>
                                <li class="{% if current_url_name == 'status_list' %}sub-active{% endif %}"><a href="{% url 'invoice:status_list' %}"><i class="fas fa-info-circle"></i>الحالات</a></li>
                                <li class="{% if current_url_name == 'price_type_list' %}sub-active{% endif %}"><a href="{% url 'invoice:price_type_list' %}"><i class="fas fa-tags"></i>أنواع الأسعار</a></li>
                            </ul>
                        </li>
                        {% endif %}
                    </ul>
                </div>
            </div>

            <div class="navbar-left-section">
                <a href="{% url 'invoice:cart_detail' %}" id="cartBtn" class="nav-action-btn tw-hidden sm:tw-inline-flex" title="سلة التسوق">
                    <i class="fas fa-shopping-cart"></i>
                    {% if cart_count > 0 %}
                    <span class="nav-badge green">{{ cart_count }}</span>
                    {% endif %}
                </a>
                {% if request.user.is_superuser and unread_notifications_count > 0 %}
                <a href="{% url 'invoice:admin_stock_notifications' %}" id="notificationBtn" class="nav-action-btn tw-hidden sm:tw-inline-flex" title="الإشعارات">
                    <i class="fas fa-bell"></i>
                    <span class="nav-badge red">{{ unread_notifications_count }}</span>
                </a>
                {% endif %}

                <span class="nav-username d-none d-md-inline-block" title="{{ user.get_full_name|default:user.username }}">
                    {{ user.get_full_name|default:user.username }}
                </span>

                <div class="user-dropdown">
                    <div class="user-dropdown-trigger" id="userMenuBtn">
                        {% if user_profile_picture != '/static/images/default_avatar.png' %}
                            <img src="{{ user_profile_picture }}" alt="صورة المستخدم" loading="lazy">
                        {% else %}
                            <i class="fas fa-user"></i>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>
    </nav>

    <!-- ✅ القائمة المنسدلة: عنصر منفصل خارج الـ nav تماماً كما في القالب الأصلي -->
    <div class="user-dropdown-backdrop" id="userDropdownBackdrop"></div>
    <div class="user-dropdown-menu" id="userDropdown">
        <div class="ud-header">
            <p class="ud-name">{{ user.get_full_name|default:user.username }}</p>
            <p class="ud-role">{% if user.is_staff %}موظف{% else %}مستخدم{% endif %}</p>
        </div>
        <div class="ud-login-info">
            <i class="fas fa-clock"></i>
            <span>آخر دخول:</span>
            <strong>{{ user_last_login }}</strong>
        </div>
        <div class="ud-links">
            <a href="{% url 'accounts:profile' %}"><i class="fas fa-user-circle"></i>الملف الشخصي</a>
            <a href="{% url 'accounts:change_password' %}"><i class="fas fa-key"></i>تغيير كلمة المرور</a>
            {% if request.user.is_superuser %}
            <a href="{% url 'accounts:company_settings' %}"><i class="fas fa-building"></i>إعدادات الشركة</a>
            {% endif %}
            <hr>
            <form action="{% url 'accounts:logout' %}" method="post">
                {% csrf_token %}
                <button type="submit" class="ud-logout"><i class="fas fa-sign-out-alt"></i>تسجيل الخروج</button>
            </form>
        </div>
    </div>

    <div class="sidebar-overlay" id="sidebarOverlay"></div>
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-login-bar">
            <i class="fas fa-clock"></i>
            <span class="sl-label">آخر دخول</span>
            <span class="sl-value">{{ user_last_login }}</span>
        </div>
        <ul class="sidebar-menu">
            <li class="sidebar-item">
                <a href="{% url 'index' %}" class="sidebar-link {% if current_url_name == 'index' %}active{% endif %}">
                    <i class="fas fa-home sidebar-icon"></i><span class="sidebar-text">الرئيسية</span>
                </a>
            </li>
            <li class="sidebar-item has-dropdown {% if 'purch' in current_url_name or 'sale' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-file-invoice sidebar-icon"></i><span class="sidebar-text">الفواتير</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    {% if perms.invoice.add_purch %}
                    <li class="sidebar-item"><a href="{% url 'invoice:purch_create' %}" class="sidebar-link"><i class="fas fa-plus-circle sidebar-icon"></i><span class="sidebar-text">إنشاء فاتورة شراء</span></a></li>
                    {% endif %}
                    {% if perms.invoice.view_purch %}
                    <li class="sidebar-item"><a href="{% url 'invoice:purch_list' %}" class="sidebar-link"><i class="fas fa-list sidebar-icon"></i><span class="sidebar-text">قائمة فواتير المشتريات</span></a></li>
                    {% endif %}
                    {% if perms.invoice.add_sale %}
                    <li class="sidebar-item"><a href="{% url 'invoice:sale_create' %}" class="sidebar-link"><i class="fas fa-plus-circle sidebar-icon"></i><span class="sidebar-text">إنشاء فاتورة بيع</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:pos_sale_create' %}" class="sidebar-link pos-quick-link"><i class="fas fa-cash-register sidebar-icon"></i><span class="sidebar-text">نقطة بيع سريعة (F4)</span></a></li>
                    {% endif %}
                    {% if perms.invoice.view_sale %}
                    <li class="sidebar-item"><a href="{% url 'invoice:sale_list' %}" class="sidebar-link"><i class="fas fa-list sidebar-icon"></i><span class="sidebar-text">قائمة فواتير المبيعات</span></a></li>
                    {% endif %}
                    {% if perms.invoice.view_purchreturn %}
                    <li class="sidebar-item"><a href="{% url 'invoice:purchase_return_list' %}" class="sidebar-link"><i class="fas fa-undo sidebar-icon"></i><span class="sidebar-text">مرتجعات المشتريات</span></a></li>
                    {% endif %}
                    {% if perms.invoice.view_salereturn %}
                    <li class="sidebar-item"><a href="{% url 'invoice:sale_return_list' %}" class="sidebar-link"><i class="fas fa-receipt sidebar-icon"></i><span class="sidebar-text">مرتجعات المبيعات</span></a></li>
                    {% endif %}
                </ul>
            </li>
            {% if perms.invoice.view_product %}
            <li class="sidebar-item has-dropdown {% if 'product' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-boxes sidebar-icon"></i><span class="sidebar-text">المنتجات</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    <li class="sidebar-item"><a href="{% url 'invoice:product_list' %}" class="sidebar-link"><i class="fas fa-list sidebar-icon"></i><span class="sidebar-text">قائمة المنتجات</span></a></li>
                    {% if perms.invoice.add_product %}
                    <li class="sidebar-item"><a href="{% url 'invoice:product_create' %}" class="sidebar-link"><i class="fas fa-plus-circle sidebar-icon"></i><span class="sidebar-text">إضافة منتج</span></a></li>
                    {% endif %}
                    <li class="sidebar-item"><a href="{% url 'invoice:barcode_statement' %}#barcode-section" class="sidebar-link"><i class="fas fa-barcode sidebar-icon"></i><span class="sidebar-text">إدارة الباركود</span></a></li>
                    {% if perms.invoice.change_product %}
                    <li class="sidebar-item"><a href="{% url 'invoice:product_bulk_update' %}" class="sidebar-link"><i class="fas fa-tags sidebar-icon"></i><span class="sidebar-text">نظام التسعير</span></a></li>
                    {% endif %}
                </ul>
            </li>
            {% endif %}
            <li class="sidebar-item has-dropdown {% if 'orders' in current_url_name or 'store' in current_url_name or 'checkout' in current_url_name or 'notification' in current_url_name or 'cart' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-store sidebar-icon"></i><span class="sidebar-text">المتجر الإلكتروني</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    {% if perms.invoice.view_order %}
                    <li class="sidebar-item"><a href="{% url 'invoice:orders_list' %}" class="sidebar-link"><i class="fas fa-inbox sidebar-icon"></i><span class="sidebar-text">إدارة الطلبات</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:admin_stock_notifications' %}" class="sidebar-link"><i class="fas fa-bell sidebar-icon"></i><span class="sidebar-text">تنبيهات المخزون</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:notification_archive' %}" class="sidebar-link"><i class="fas fa-history sidebar-icon"></i><span class="sidebar-text">أرشيف الإشعارات</span></a></li>
                    {% endif %}
                    {% if perms.invoice.change_order %}
                    <li class="sidebar-item"><a href="{% url 'invoice:control_store' %}" class="sidebar-link"><i class="fas fa-sliders-h sidebar-icon"></i><span class="sidebar-text">إدارة المتجر</span></a></li>
                    {% endif %}
                    <li class="sidebar-item"><a href="{% url 'invoice:store_front' %}" class="sidebar-link" target="_blank" rel="nofollow noopener noreferrer"><i class="fas fa-external-link-alt sidebar-icon"></i><span class="sidebar-text">واجهة المتجر</span></a></li>
                    {% if perms.invoice.view_order %}
                    <li class="sidebar-item"><a href="{% url 'invoice:checkout' %}" class="sidebar-link"><i class="fas fa-credit-card sidebar-icon"></i><span class="sidebar-text">صفحة الدفع</span></a></li>
                    {% endif %}
                    <li class="sidebar-item">
                        <a href="{% url 'invoice:cart_detail' %}" class="sidebar-link">
                            <i class="fas fa-shopping-cart sidebar-icon"></i><span class="sidebar-text">سلة التسوق</span>
                            {% if cart_count > 0 %}
                            <span class="sidebar-cart-count">{{ cart_count }}</span>
                            {% endif %}
                        </a>
                    </li>
                </ul>
            </li>
            {% if perms.invoice.view_cashtransaction %}
            <li class="sidebar-item has-dropdown {% if 'cash' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-wallet sidebar-icon"></i><span class="sidebar-text">الصندوق</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    <li class="sidebar-item"><a href="{% url 'invoice:cash_transaction_list' %}" class="sidebar-link"><i class="fas fa-exchange-alt sidebar-icon"></i><span class="sidebar-text">حركة الصندوق</span></a></li>
                    {% if perms.invoice.add_cashtransaction %}
                    <li class="sidebar-item"><a href="{% url 'invoice:cash_transaction_create' %}" class="sidebar-link"><i class="fas fa-hand-holding-usd sidebar-icon"></i><span class="sidebar-text">حركة مالية</span></a></li>
                    {% endif %}
                </ul>
            </li>
            {% endif %}
            {% if request.user.is_superuser %}
            <li class="sidebar-item has-dropdown {% if 'report' in current_url_name or 'statement' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-chart-bar sidebar-icon"></i><span class="sidebar-text">التقارير</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    <li class="sidebar-item"><a href="{% url 'invoice:profit_report' %}" class="sidebar-link"><i class="fas fa-chart-line sidebar-icon"></i><span class="sidebar-text">تقرير الأرباح</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:daily_sales_summary' %}" class="sidebar-link"><i class="fas fa-calendar-day sidebar-icon"></i><span class="sidebar-text">ملخص المبيعات اليومي</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:sales_by_customer_report' %}" class="sidebar-link"><i class="fas fa-users sidebar-icon"></i><span class="sidebar-text">مبيعات العملاء</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:purchases_by_supplier_report' %}" class="sidebar-link"><i class="fas fa-truck sidebar-icon"></i><span class="sidebar-text">مشتريات الموردين</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:unpaid_invoices_report' %}" class="sidebar-link"><i class="fas fa-file-invoice-dollar sidebar-icon"></i><span class="sidebar-text">فواتير غير مسددة</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:unpaid_sales_report' %}" class="sidebar-link"><i class="fas fa-exclamation-triangle sidebar-icon"></i><span class="sidebar-text">الديون المتراكمة</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:dead_stock_report' %}" class="sidebar-link"><i class="fas fa-box-open sidebar-icon"></i><span class="sidebar-text">منتجات راكدة</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:barcode_statement' %}" class="sidebar-link"><i class="fas fa-barcode sidebar-icon"></i><span class="sidebar-text">حركة الباركود</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:statement_report' %}" class="sidebar-link"><i class="fas fa-file-alt sidebar-icon"></i><span class="sidebar-text">كشف حساب</span></a></li>
                </ul>
            </li>
            {% endif %}
            {% if perms.auth.view_user %}
            <li class="sidebar-item has-dropdown {% if 'user' in current_url_name or 'register' in current_url_name or 'permissions' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-users-cog sidebar-icon"></i><span class="sidebar-text">المستخدمين</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    <li class="sidebar-item"><a href="{% url 'accounts:user_list' %}" class="sidebar-link"><i class="fas fa-list sidebar-icon"></i><span class="sidebar-text">قائمة المستخدمين</span></a></li>
                    {% if perms.auth.add_user %}
                    <li class="sidebar-item"><a href="{% url 'accounts:register' %}" class="sidebar-link"><i class="fas fa-user-plus sidebar-icon"></i><span class="sidebar-text">إضافة مستخدم جديد</span></a></li>
                    {% endif %}
                    {% if request.user.is_superuser %}
                    <li class="sidebar-item"><a href="{% url 'accounts:permissions' %}" class="sidebar-link"><i class="fas fa-user-shield sidebar-icon"></i><span class="sidebar-text">الصلاحيات والأدوار</span></a></li>
                    {% endif %}
                </ul>
            </li>
            {% endif %}
            {% if request.user.is_superuser %}
            <li class="sidebar-item has-dropdown {% if 'currency' in current_url_name or 'payment_method' in current_url_name or 'shipping_company' in current_url_name or 'status' in current_url_name or 'price_type' in current_url_name or 'email_settings' in current_url_name %}active{% endif %}">
                <a href="#" class="sidebar-link">
                    <i class="fas fa-cogs sidebar-icon"></i><span class="sidebar-text">الإعدادات</span>
                    <i class="fas fa-chevron-left sidebar-arrow"></i>
                </a>
                <ul class="sidebar-dropdown">
                    <li class="sidebar-item"><a href="{% url 'invoice:email_settings' %}" class="sidebar-link"><i class="fas fa-envelope-open-text sidebar-icon"></i><span class="sidebar-text">إعدادات البريد</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:currency_list' %}" class="sidebar-link"><i class="fas fa-dollar-sign sidebar-icon"></i><span class="sidebar-text">العملات</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:payment_method_list' %}" class="sidebar-link"><i class="fas fa-credit-card sidebar-icon"></i><span class="sidebar-text">طرق الدفع</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:shipping_company_list' %}" class="sidebar-link"><i class="fas fa-truck sidebar-icon"></i><span class="sidebar-text">شركات الشحن</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:status_list' %}" class="sidebar-link"><i class="fas fa-info-circle sidebar-icon"></i><span class="sidebar-text">الحالات</span></a></li>
                    <li class="sidebar-item"><a href="{% url 'invoice:price_type_list' %}" class="sidebar-link"><i class="fas fa-tags sidebar-icon"></i><span class="sidebar-text">أنواع الأسعار</span></a></li>
                </ul>
            </li>
            {% endif %}
        </ul>
    </aside>

    <main class="main-content">
        {% block content %}{% endblock %}
    </main>

    <footer class="footer">
        <div class="footer-container">
            <div class="row">
                <div class="col-md-4 mb-3 mb-md-0">
                    <div class="footer-logo">
                        <div class="f-logo">
                            {% if company_settings and company_settings.company_logo %}
                                <img src="{{ company_settings.company_logo.url }}" alt="شعار الشركة" loading="lazy">
                            {% else %}
                                <i class="fas fa-file-invoice-dollar"></i>
                            {% endif %}
                        </div>
                        <span class="footer-logo-text">{{ company_settings.company_name|default:"نظام إدارة الفواتير" }}</span>
                    </div>
                    <div class="social-links">
                        {% if company_settings and company_settings.facebook %}<a href="{{ company_settings.facebook }}" target="_blank" rel="nofollow noopener noreferrer"><i class="fab fa-facebook-f"></i></a>{% endif %}
                        {% if company_settings and company_settings.twitter %}<a href="{{ company_settings.twitter }}" target="_blank" rel="nofollow noopener noreferrer"><i class="fab fa-twitter"></i></a>{% endif %}
                        {% if company_settings and company_settings.instagram %}<a href="{{ company_settings.instagram }}" target="_blank" rel="nofollow noopener noreferrer"><i class="fab fa-instagram"></i></a>{% endif %}
                        {% if company_settings and company_settings.whatsapp %}<a href="https://wa.me/{{ company_settings.whatsapp }}" target="_blank" rel="nofollow noopener noreferrer"><i class="fab fa-whatsapp"></i></a>{% endif %}
                    </div>
                </div>
                <div class="col-md-4 mb-3 mb-md-0">
                    <div class="footer-links">
                        <h6>روابط سريعة</h6>
                        <ul>
                            <li><a href="{% url 'index' %}"><i class="fas fa-home"></i>الرئيسية</a></li>
                            {% if perms.invoice.view_sale %}<li><a href="{% url 'invoice:sale_list' %}"><i class="fas fa-file-invoice"></i>الفواتير</a></li>{% endif %}
                            {% if perms.invoice.view_product %}<li><a href="{% url 'invoice:product_list' %}"><i class="fas fa-boxes"></i>المنتجات</a></li>{% endif %}
                            <li><a href="{% url 'invoice:store_front' %}" target="_blank" rel="nofollow noopener noreferrer"><i class="fas fa-store"></i>المتجر</a></li>
                        </ul>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="footer-links">
                        <h6>تواصل معنا</h6>
                        <ul class="footer-contact">
                            {% if company_settings and company_settings.phone %}
                            <li><a href="tel:{{ company_settings.phone }}"><i class="fas fa-phone"></i>{{ company_settings.phone }}</a></li>
                            {% endif %}
                            {% if company_settings and company_settings.email %}
                            <li><a href="mailto:{{ company_settings.email }}"><i class="fas fa-envelope"></i>{{ company_settings.email }}</a></li>
                            {% endif %}
                            {% if company_settings and company_settings.address %}
                            <li><a href="#"><i class="fas fa-map-marker-alt"></i>{{ company_settings.address }}</a></li>
                            {% endif %}
                        </ul>
                    </div>
                </div>
            </div>
            <div class="footer-bottom">
                <div class="row align-items-center">
                    <div class="col-md-6">
                        <span>جميع الحقوق محفوظة &copy; {{ company_settings.company_name|default:"الشركة" }} {% now "Y" %}</span>
                    </div>
                    <div class="col-md-6 footer-copyright-left">
                        <span>نظام إدارة الفواتير v1.0</span>
                    </div>
                </div>
            </div>
        </div>
    </footer>

    {% else %}
    <main class="main-content d-flex align-items-center justify-content-center auth-main-content">
        {% block auth_content %}{% endblock %}
    </main>
    {% endif %}

    {% if company_settings and company_settings.whatsapp %}
    <div class="wa-float-container" id="waFloat">
        <span class="wa-float-msg" id="waFloatMsg">تواصل معنا عبر واتساب</span>
        <a href="https://wa.me/{{ company_settings.whatsapp }}" class="wa-float-btn" target="_blank" rel="nofollow noopener noreferrer" aria-label="تواصل عبر واتساب">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
        </a>
    </div>
    {% endif %}

    <script nonce="{{ csp_nonce }}">
    (function() {
        'use strict';

        var sidebar = document.getElementById('sidebar');
        var sidebarOverlay = document.getElementById('sidebarOverlay');
        var menuToggle = document.getElementById('menuToggle');

        function openSidebar() {
            if (!sidebar) return;
            sidebar.classList.add('active');
            if (sidebarOverlay) sidebarOverlay.classList.add('active');
            if (menuToggle) { menuToggle.classList.add('active'); menuToggle.setAttribute('aria-expanded', 'true'); }
            document.body.style.overflow = 'hidden';
        }
        function closeSidebar() {
            if (!sidebar) return;
            sidebar.classList.remove('active');
            if (sidebarOverlay) sidebarOverlay.classList.remove('active');
            if (menuToggle) { menuToggle.classList.remove('active'); menuToggle.setAttribute('aria-expanded', 'false'); }
            document.body.style.overflow = '';
        }
        if (menuToggle) {
            menuToggle.addEventListener('click', function() {
                if (sidebar && sidebar.classList.contains('active')) { closeSidebar(); } else { openSidebar(); }
            });
        }
        if (sidebarOverlay) { sidebarOverlay.addEventListener('click', closeSidebar); }
        var mql = window.matchMedia('(min-width: 993px)');
        function handleScreenChange(e) { if (e.matches) closeSidebar(); }
        if (mql.addEventListener) { mql.addEventListener('change', handleScreenChange); }
        else if (mql.addListener) { mql.addListener(handleScreenChange); }

        var sidebarDropdowns = document.querySelectorAll('.sidebar-item.has-dropdown > .sidebar-link');
        sidebarDropdowns.forEach(function(link) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                var parent = this.parentElement;
                var isActive = parent.classList.contains('active');
                document.querySelectorAll('.sidebar-item.has-dropdown.active').forEach(function(item) {
                    if (item !== parent) item.classList.remove('active');
                });
                parent.classList.toggle('active', !isActive);
            });
        });

        /* ===== القائمة المنسدلة للمستخدم — مطابقة القالب الأصلي تماماً ===== */
        var userMenuBtn = document.getElementById('userMenuBtn');
        var userDropdown = document.getElementById('userDropdown');
        var userDropdownBackdrop = document.getElementById('userDropdownBackdrop');

        function openUserDropdown() {
            if (!userDropdown || !userMenuBtn) return;
            if (window.innerWidth > 768) {
                var btnRect = userMenuBtn.getBoundingClientRect();
                var dropdownWidth = userDropdown.offsetWidth;
                /* حساب الموضع: الحافة اليمنى للقائمة تطابق حافة الزر اليمنى */
                userDropdown.style.top = (btnRect.bottom + 8) + 'px';
                userDropdown.style.right = (window.innerWidth - btnRect.right) + 'px';
                userDropdown.style.left = 'auto';
                userDropdown.bottom = 'auto';
            }
            userDropdown.classList.add('show');
            if (userDropdownBackdrop) userDropdownBackdrop.classList.add('active');
        }
        function closeUserDropdown() {
            if (!userDropdown) return;
            userDropdown.classList.remove('show');
            if (userDropdownBackdrop) userDropdownBackdrop.classList.remove('active');
        }
        if (userMenuBtn) {
            userMenuBtn.addEventListener('click', function(e) {
                e.stopPropagation();
                if (userDropdown && userDropdown.classList.contains('show')) { closeUserDropdown(); } else { openUserDropdown(); }
            });
            userMenuBtn.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.click(); }
            });
        }
        if (userDropdownBackdrop) { userDropdownBackdrop.addEventListener('click', closeUserDropdown); }
        document.addEventListener('click', function(e) {
            if (userDropdown && userDropdown.classList.contains('show')) {
                if (!userDropdown.contains(e.target) && e.target !== userMenuBtn) { closeUserDropdown(); }
            }
        });
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') { closeUserDropdown(); closeSidebar(); }
        });

        /* ===== مؤشر التبويب النشط ===== */
        var horiSelector = document.querySelector('.hori-selector');
        var navLinks = document.querySelectorAll('#navbarSupportedContent > ul > li');
        function updateHoriSelector(activeLi) {
            if (!horiSelector || !activeLi) return;
            var navContainer = document.getElementById('navbarSupportedContent');
            if (!navContainer) return;
            var navRect = navContainer.getBoundingClientRect();
            var liRect = activeLi.getBoundingClientRect();
            horiSelector.style.width = liRect.width + 'px';
            horiSelector.style.left = (liRect.left - navRect.left) + 'px';
            horiSelector.style.display = 'inline-block';
        }
        var activeLi = document.querySelector('#navbarSupportedContent > ul > li.active');
        if (activeLi) { setTimeout(function() { updateHoriSelector(activeLi); }, 100); }
        navLinks.forEach(function(li) {
            li.addEventListener('mouseenter', function() { updateHoriSelector(this); });
        });
        var navContainer = document.getElementById('navbarSupportedContent');
        if (navContainer) {
            navContainer.addEventListener('mouseleave', function() {
                var current = document.querySelector('#navbarSupportedContent > ul > li.active');
                if (current) { updateHoriSelector(current); } else if (horiSelector) { horiSelector.style.display = 'none'; }
            });
        }
        var resizeTimer;
        window.addEventListener('resize', function() {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(function() {
                var current = document.querySelector('#navbarSupportedContent > ul > li.active');
                if (current) updateHoriSelector(current);
                /* إعادة حساب موقع القائمة المنسدلة عند تغيير حجم النافذة */
                if (userDropdown && userDropdown.classList.contains('show') && window.innerWidth > 768) { openUserDropdown(); }
            }, 150);
        });

        /* ===== إخفاء رسالة واتساب بعد 8 ثوانٍ ===== */
        var waMsg = document.getElementById('waFloatMsg');
        if (waMsg) {
            setTimeout(function() {
                waMsg.classList.add('wa-float-msg-hide');
                setTimeout(function() { waMsg.style.display = 'none'; }, 500);
            }, 8000);
        }
    })();
    </script>

    {% block extra_js %}{% endblock %}

    {% block chart_js %}{% endblock %}
</body>
</html>