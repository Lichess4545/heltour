
function parse_model() {
	var $table = $('#table-edit-rosters');
	var board_count = parseInt($table.attr('data-boards'));
	var teams = [];
	var team_number_offset = 0;
	
	$.each($table.find('.team'), function () {
		var $team = $(this);
		var team_number = parseInt($team.attr('data-number')) - team_number_offset;
		var $team_name = $team.find('.team-name');
		var team = {
			name: $team_name.is('.default-name') ? 'Team ' + team_number : $team_name.text(),
			number: team_number,
			boards: []
		};
		var has_player = false;
		$.each($team.find('[data-board]'), function () {
			var $board = $(this);
			var $player = $board.find('.player');
			if (!$player.length) {
				team.boards.push(null);
				return;
			}
			var player = {
				name: $player.find('.name').text(),
				is_captain: $player.find('.extra').text().contains('C')
			};
			team.boards.push(player);
			has_player = true;
		});
		if (has_player || !$team.is('.new-team')) {
			teams.push(team);
		} else {
			team_number_offset++;
		}
	});
	
	return {
		board_count: board_count,
		teams: teams
	};
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
			var $target = $(this);
			var $target_team = $target.closest('.team');
			var $other_player = $target_team.length > 0 ? $target.find('.player') : [];
			
			var $source_team = $source.closest('.team');
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
			
			if ($target_team.length > 0 && $target_team.is('.new-team-template')) {
				$new_team = $target_team.clone();
				$target_team.after($new_team);
				var num = parseInt($new_team.attr('data-number')) + 1;
				$new_team.attr('data-number', num);
				$new_team.find('.team-name').text('Team ' + num);
				setUpDropEvents($new_team.find('[data-board]'));
				$target_team.removeClass('new-team-template');
			}
			
			if ($target_team.length > 0) {
				$target.append($player);
			} else {
				var $tr = $('<tr><td></td></tr>')
				$target.closest('table').append($tr);
				$tr.find('td').append($player);
			}
			
			// TODO: Update average ratings
			
			setTimeout(function() {
				$player.add($other_player).stop().css("background-color", "orange").animate({ backgroundColor: "#FFFFFF"}, 1000);
			}, 1)
		}
	});
}

$(function() {
	var initial = parse_model();
	
	$('#form-edit-rosters').submit(function(e) {
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
		    				 || old_player.is_captain != new_player.is_captain) {
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
	     
	     $('#id_changes').val(JSON.stringify(changes));
	});
	
	setUpDragEvents($('.player'));
	
	setUpDropEvents($('[data-board], .table-drop'));
	
	$('body').on('click', '.team-name', function(e) {
		$team_name = $(this);
		team_name = $team_name.text();
		$edit = $('<input type="text" class="team-name-edit">');
		$edit.val(team_name);
		$team_name.after($edit);
		$team_name.hide();
		$edit.focus();
		$edit.on('blur', function() {
			$team_name.text($edit.val());
			$edit.remove();
			$team_name.show();
		});
	});
});
