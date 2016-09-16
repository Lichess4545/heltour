// Parse a model object from the HTML
function parse_model() {
	var $table_teams = $('#table-edit-rosters');
	var board_count = parseInt($table_teams.attr('data-boards'));
	var teams = [];
	
	$.each($table_teams.find('.team').not('.new-team-template'), function () {
		var $team = $(this);
		var team_number = parseInt($team.attr('data-number'));
		var $team_name = $team.find('.team-name');
		var team = {
			name: $team_name.text(),
			number: team_number,
			boards: []
		};
		$.each($team.find('[data-board]'), function () {
			var $board = $(this);
			var $player = $board.find('.player');
			if (!$player.length) {
				team.boards.push(null);
				return;
			}
			var extra_text = $player.find('.extra').text();
			var player = {
				name: $player.find('.name').text(),
				is_captain: extra_text.indexOf('C') !== -1,
				is_vice_captain: extra_text.indexOf('V') !== -1
			};
			team.boards.push(player);
		});
		teams.push(team);
	});
	
	var $table_alt = $('#table-alternates');
	var alternates = [];
	
	$.each($table_alt.find('[data-board]'), function () {
		var $board = $(this);
		var alt_list = [];
		$.each($board.find('.player'), function () {
			var $player = $(this);
			var player = {
				name: $player.find('.name').text()
			};
			alt_list.push(player);
		});
		alternates.push(alt_list);
	});
	
	return {
		board_count: board_count,
		teams: teams,
		alternates: alternates
	};
}

// Determine a list of changes from the current model compared to the provided model
function detect_changes(initial) {
	var current = parse_model();
	var changes = [];
	
	for (var team_num = 0; team_num < current.teams.length; team_num++) {
		var old_team = initial.teams[team_num];
		var new_team = current.teams[team_num];
		if (!old_team) {
			changes.push({
				action: 'create-team',
				model: new_team
			});
		} else {
			if (old_team.name !== new_team.name) {
				changes.push({
					action: 'change-team',
					team_number: new_team.number,
					team_name: new_team.name
				});
			}
			for (var board_num = 0; board_num < current.board_count; board_num++) {
				var old_player = old_team.boards[board_num];
				var new_player = new_team.boards[board_num];
				if (old_player === null && new_player === null) {
					continue;
				}
				if (old_player === null || new_player === null
						|| old_player.name != new_player.name
						|| old_player.is_captain != new_player.is_captain
						|| old_player.is_vice_captain != new_player.is_vice_captain) {
					changes.push({
						action: 'change-member',
						team_number: new_team.number,
						board_number: board_num + 1,
						player: new_player
					});
				}
			}
		}
	}
	
	for (var board_num = 0; board_num < current.board_count; board_num++) {
		var old_alt_list = initial.alternates[board_num];
		var new_alt_list = current.alternates[board_num];
		var old_names = {};
		$.each(old_alt_list, function() {
			old_names[this.name] = this;
		});
		$.each(new_alt_list, function() {
			if (this.name in old_names) {
				delete old_names[this.name];
			} else {
				changes.push({
					action: 'create-alternate',
					board_number: board_num + 1,
					player_name: this.name
				});
			}
		});
		$.each(old_names, function() {
			changes.push({
				action: 'delete-alternate',
				board_number: board_num + 1,
				player_name: this.name
			});
		});
	}
	
	return changes;
}

// Recalculate the average rating for the speciifed team
function updateAverage($teams) {
	for (var i = 0; i < $teams.length; i++) {
		$team = $($teams[i]);
		var $players = $team.find('.player');
		var n = 0;
		var total = 0.0;
		var nExp = 0;
		var totalExp = 0.0;
		for (var j = 0; j < $players.length; j++) {
			var rating = parseInt($players.eq(j).find('.rating').text());
			if (!isNaN(rating)) {
				n += 1;
				total += rating;
			}
			var ratingExp = parseInt($players.eq(j).attr('data-exp-rating'));
			if (!isNaN(ratingExp)) {
				nExp += 1;
				totalExp += ratingExp;
			}
		}
		if (n > 0) {
			$team.find('.average-rating').text((total / n).toFixed(2));
		} else {
			$team.find('.average-rating').text('');
		}
		if (nExp > 0) {
			$team.find('.average-exp-rating').text((totalExp / nExp).toFixed(2));
		} else {
			$team.find('.average-exp-rating').text('');
		}
	}
}

function setUpDragEvents($players) {
	$players.draggable({
		revert: true,
		revertDuration: 0
	});
}

function setUpDropEvents($boards) {
	$boards.droppable({
		drop: function (event, ui) {
			var $player = ui.draggable;
			var $source = $player.parent();
			var $source_team = $source.closest('.team');
			var $target = $(this);
			var $target_team = $target.closest('.team');
			var $other_player = $target_team.length > 0 ? $target.find('.player') : [];
			var changing_teams = ($source_team[0] !== $target_team[0]);
			
			// Update the source of the drag
			if ($source_team.length === 0) {
				var $row = $player.closest('tr');
				$player.detach();
				if ($other_player.length > 0) {
					$other_player.detach();
					$source.append($other_player);
				} else {
					$row.remove();
				}
			} else {
				$player.detach();
				if ($other_player.length > 0) {
					$other_player.detach();
					$source.append($other_player);
				}
			}
			
			// If the target of the drag is a new team, clone the template in case the user wants to create more teams
			if ($target_team.length > 0 && $target_team.is('.new-team-template')) {
				$new_team = $target_team.clone();
				$target_team.after($new_team);
				var num = parseInt($new_team.attr('data-number')) + 1;
				$new_team.attr('data-number', num);
				$new_team.find('.team-name').text('Team ' + num);
				setUpDropEvents($new_team.find('[data-board]'));
				$target_team.removeClass('new-team-template');
			}
			
			// Update the target of the drag
			if ($target_team.length > 0) {
				$target.append($player);
			} else {
				var $tr = $('<tr><td></td></tr>')
				$target.find('table').append($tr);
				$tr.find('td').append($player);
			}
			
			// Delete empty unsaved teams at the end of the list (before the template)
			var $next_team = $source_team.next();
			if (changing_teams && $next_team.is('.new-team-template')) {
				var $team_to_remove = $source_team;
				while ($team_to_remove.length > 0 && $team_to_remove.is('.new-team')
						&& $team_to_remove.find('.player').length === 0) {
					var $prev = $team_to_remove.prev();
					var num = parseInt($team_to_remove.attr('data-number'));
					$team_to_remove.remove();
					$next_team.attr('data-number', num);
					$next_team.find('.team-name').text('Team ' + num);
					$team_to_remove = $prev;
				}
			}
			
			// Update average ratings
			updateAverage($source_team);
			updateAverage($target_team);
			
			// Animate the moved player(s)
			setTimeout(function() {
				$player.add($other_player).stop().css("background-color", "orange").animate({ backgroundColor: "#FFFFFF"}, 1000);
			}, 1)
		}
	});
}

function initPopover($el, content) {
	$el.popover({
		container: 'body',
		content: content,
		html: true,
		placement: function (ctx, source) {
	        var right = $(window).width() - ($(source).offset().left + $(source).outerWidth());
	        return right > 300 ? 'right' : 'left';
        },
		title: function() {
			var player_name = $(this).find('.name').text();
			var url = $(this).attr('data-url');
			return $('<a></a>').attr('href', url).attr('target', '_blank').text(player_name);
		},
		trigger: 'click',
	});
}

function setUpPopovers($players) {
	var $spinner = $('#spinner-template').clone().show();
	// Init popovers
	initPopover($players, $spinner);
	// Handle the popover generation
	$players.on('shown.bs.popover', function() {
		var $player = $(this);
		var popover = $player.data('bs.popover');
		var $extra = $player.find('.extra');
		
		// Populate checkboxes
		var $captain = popover.$tip.find('.captain-checkbox');
		$captain.prop('checked', $extra.text().indexOf('(C)') !== -1);
		var $vice_captain = popover.$tip.find('.vice-captain-checkbox');
		$vice_captain.prop('checked', $extra.text().indexOf('(V)') !== -1);
		
		// Set up checkbox events
		$captain.click(function() {
			if ($captain.prop('checked')) {
				$vice_captain.prop('checked', false);
				$extra.text('(C)');
			} else {
				$extra.text('');
			}
		});
		$vice_captain.click(function() {
			if ($vice_captain.prop('checked')) {
				$captain.prop('checked', false);
				$extra.text('(V)');
			} else {
				$extra.text('');
			}
		});
		
		if ($player.closest('#table-edit-rosters').length === 0) {
			// Not in a team so don't display captain checkboxes
			$captain.closest('tr').add($vice_captain.closest('tr')).hide();
		}
		
		if (!$player.data('has_info')) {
			// Pull the popover content from the server
			var url = $player.attr('data-info-url');
			$.get(url, function(data) {
				$player.data('has_info', true);
				$player.popover('destroy');
				initPopover($player, data);
				$player.popover('show');
			});
		}
	});
	// Close popovers when the user clicks outside 
	$('body').on('mousedown', function(e) {
	    if ($(e.target).parents('.popover.in').length === 0) { 
	        $('[data-toggle="popover"]').popover('hide');
	    }
	});
}

$(function() {
	var initial = parse_model();
	
	// Populate the form with the actual data in JSON format before submitting
	$('#form-edit-rosters').submit(function(e) {
		var changes = detect_changes(initial);
		$('#id_changes').val(JSON.stringify(changes));
		$(window).off('beforeunload');
	});
	
	setUpDragEvents($('.player'));
	
	setUpPopovers($('.player'));
	
	setUpDropEvents($('#table-edit-rosters [data-board], .table-drop'));
	
	updateAverage($('.team'));
	
	// Allow team names to be edited by clicking on them
	$('body').on('click', '.team-name-editable', function(e) {
		var $team_name = $(this);
		var team_name = $team_name.text();
		var $edit = $('<input type="text" class="team-name-edit">');
		$edit.val(team_name);
		$team_name.after($edit);
		$team_name.hide();
		$edit.focus();
		var hideEdit = function() {
			$team_name.text($edit.val());
			$edit.remove();
			$team_name.show();
		};
		$edit.on('keydown', function(e) {
			if (e.keyCode == 13 || e.keyCode == 27) {
				hideEdit();
				return false;
			}
		});
		$edit.on('blur', hideEdit);
	});
	
	// Check for unsaved changes
	$(window).on('beforeunload', function() {
		if (detect_changes(initial).length > 0) {
			return 'Are you sure you want to leave? You have unsaved changes.';
		}
	});
});
