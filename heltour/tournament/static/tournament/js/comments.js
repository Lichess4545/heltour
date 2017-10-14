var $ = $ || django.jQuery;
$(function() {
	$('form[action="/comments/post/"]').submit(function(e) {
		var $form = $(this);
		$.ajax({
			type: "POST",
			url: $form.attr('action'),
			data: $form.serialize(),
			success: function(data) {
				var $data = $(data);
				$('.comment-list').replaceWith($data.find('.comment-list'));
				$form.html($data.find('form[action="/comments/post/"]').html());
			}
		});
		e.preventDefault();
	});
});
