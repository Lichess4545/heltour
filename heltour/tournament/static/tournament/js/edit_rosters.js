
function parse_model() {
	var $table = $('#table-edit-rosters');
	var board_count = parseInt($table.attr('data-boards'));
	var teams = [];
	
	$.each($table.find('.team'), function () {
		var $team = $(this);
		var team = {
			name: $team.text(),
			number: parseInt($team.attr('data-number')),
			boards: []
		};
		$.each($team.closest('tr').find('[data-board]'), function () {
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
		});
		teams.push(team);
	});
	
	return {
		board_count: board_count,
		teams: teams
	};
}

function setUpPlayerEvents($players) {
	$players.draggable({
        revert: true,
        revertDuration: 0
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
	
	setUpPlayerEvents($('.player'));
	
	$('[data-board]').droppable({
		drop: function (event, ui) {
			var $player = ui.draggable;
			var $source = $player.parent();
			var $target = $(this);
			var $other = $target.find('.player');
			
			$player.detach();
			$other.detach();
			$target.append($player);
			$source.append($other);
			
			setTimeout(function() {
				$player.add($other).stop().css("background-color", "orange").animate({ backgroundColor: "#FFFFFF"}, 1000);
			}, 1)
		}
	});
});
