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
		var win = window.open(href, name, 'height=700,width=1000,resizable=yes,scrollbars=yes');
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
	
	$('time').each(function(i, el) {
		var $el = $(el);
		var date = moment($el.attr('datetime'));
		$el.tooltip({
			title: date.format('llll') + ' UTC' + date.format('Z')
		});
	});
});

if ($('.cbreplay').length > 0) {
	document.write('<link rel="stylesheet" type="text/css" href="https://pgn.chessbase.com/CBReplay.css">');
	document.write('<script src="https://pgn.chessbase.com/cbreplay.js" type="text/javascript"></script>');
}