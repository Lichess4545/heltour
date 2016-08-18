$ = $ || django.jQuery;
$(function() {
	$('.popup-link').click(function() {
		var name = this.id;
		var href = this.href;
		var win = window.open(href, name, 'height=500,width=800,resizable=yes,scrollbars=yes');
		win.focus();
		return false;
	})
	
	$('.large-popup-link').click(function() {
		var name = this.id;
		var href = this.href;
		var win = window.open(href, name, 'height=650,width=900,resizable=yes,scrollbars=yes');
		win.focus();
		return false;
	})
	
	function dismissRelatedObjectPopup(win, objId) {
        win.close();
        location.reload();
    }
	window.dismissAddRelatedObjectPopup = dismissRelatedObjectPopup;
	window.dismissChangeRelatedObjectPopup = dismissRelatedObjectPopup;
	window.dismissDeleteRelatedObjectPopup = dismissRelatedObjectPopup;
});
