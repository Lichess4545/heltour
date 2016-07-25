$(function() {
	$('.popup-link').click(function() {
		var name = this.id;
		var href = this.href;
		var win = window.open(href, name, 'height=500,width=800,resizable=yes,scrollbars=yes');
		win.focus();
		return false;
	})
	
	function dismissChangeRelatedObjectPopup(win, objId) {
        win.close();
        location.reload();
    }
	window.dismissChangeRelatedObjectPopup = dismissChangeRelatedObjectPopup;
});
