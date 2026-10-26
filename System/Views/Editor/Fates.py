from __future__ import annotations

import math
import numpy
import random

from System.Services import Player
from . import Constants, WorldBuilder

# Base Scenario

class FateScenario:
    name: str = "BASE"

    def setup_world(self, simulation_widget: object) -> None:
        pass

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        pass

    def get_radar_status_text(self, simulation_widget: object) -> str:
        return Constants.FATE_TEXTS["waypoint_ok"].format(waypoint = simulation_widget.current_waypoint_index + 1)

# Specific Fate Scenarios

class StandardFate(FateScenario):
    name: str = "STANDARD"

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        if not simulation_widget.solution_path_points:
            return

        terminal_point        = simulation_widget.solution_path_points[-1]
        cell_scale            = simulation_widget.cell_scale_units
        distance_to_finish    = math.hypot(
            simulation_widget.camera_position[0] - (terminal_point[0] + 0.5) * cell_scale,
            simulation_widget.camera_position[2] - (terminal_point[1] + 0.5) * cell_scale
        )

        has_reached_threshold = (
            distance_to_finish < 4.5 or (
                simulation_widget.device_picked_up and
                simulation_widget.current_waypoint_index > len(simulation_widget.solution_path_points) * 0.65
            )
        )

        if has_reached_threshold and not simulation_widget.finale_sequence_active:
            simulation_widget.finale_sequence_active = True
            audio_pan = simulation_widget.calculate_audio_pan(
                float(simulation_widget.corridor_entrance_position[0]),
                float(simulation_widget.corridor_entrance_position[2])
            )
            Player.ui_player.play_sound(".vault/Anomaly/SparkPop", pan = audio_pan)
            simulation_widget.display_message(Constants.FATE_TEXTS["standard_warning"])

            simulation_widget.monster_entity_position    = numpy.copy(simulation_widget.corridor_entrance_position)
            simulation_widget.monster_entity_position[1] = 0.0
            simulation_widget.monster_entity_active      = True
            simulation_widget.monster_path_waypoints     = WorldBuilder.find_shortest_grid_path(
                simulation_widget.monster_entity_position,
                simulation_widget.camera_position,
                simulation_widget.world_grid_array,
                simulation_widget.cell_scale_units,
                simulation_widget.maze_dimension
            )

        if not simulation_widget.finale_sequence_active:
            return

        simulation_widget.finale_timer_seconds += delta_time_seconds
        distance_to_monster                     = math.hypot(
            simulation_widget.camera_position[0] - simulation_widget.monster_entity_position[0],
            simulation_widget.camera_position[2] - simulation_widget.monster_entity_position[2]
        )

        simulation_widget.heartbeat_timer_seconds -= delta_time_seconds

        if simulation_widget.heartbeat_timer_seconds <= 0.0:
            simulation_widget.heartbeat_timer_seconds = float(numpy.clip(distance_to_monster / 18.0, 0.22, 1.05))
            Player.ui_player.play_sound(".vault/Anomaly/Heartbeat")

        simulation_widget.monster_repath_timer -= delta_time_seconds

        if simulation_widget.monster_repath_timer <= 0.0:
            simulation_widget.monster_repath_timer   = 0.22
            simulation_widget.monster_path_waypoints = WorldBuilder.find_shortest_grid_path(
                simulation_widget.monster_entity_position,
                simulation_widget.camera_position,
                simulation_widget.world_grid_array,
                simulation_widget.cell_scale_units,
                simulation_widget.maze_dimension
            )

        simulation_widget.monster_entity_position = simulation_widget.step_entity_navigation(
            simulation_widget.monster_entity_position,
            simulation_widget.monster_path_waypoints,
            simulation_widget.monster_movement_speed * 1.30,
            delta_time_seconds,
            is_monster = True
        )

        if distance_to_monster <= 1.45:
            Player.ui_player.play_sound(".vault/Anomaly/VisceralScream")
            simulation_widget.jumpscare_blood_factor = min(1.0, simulation_widget.jumpscare_blood_factor + delta_time_seconds * 4.5)
            simulation_widget.reality_tear_ratio     = 1.0

        if distance_to_monster <= 0.88 or simulation_widget.jumpscare_blood_factor >= 0.96:
            simulation_widget.finalize_easter_egg_termination(Constants.FATE_TEXTS["standard_caught"])


class BurnoutFate(FateScenario):
    name: str = "BURNOUT"

    def setup_world(self, simulation_widget: object) -> None:
        dimension  = simulation_widget.maze_dimension
        scale_unit = simulation_widget.cell_scale_units

        minimum_bound = 12
        maximum_bound = 32
        simulation_widget.world_grid_array[minimum_bound:maximum_bound, minimum_bound:maximum_bound] = 0

        coordinate_x = 22
        coordinate_z = 22
        simulation_widget.camera_position       = numpy.array([(coordinate_x + 0.5) * scale_unit, 1.4, (coordinate_z + 0.5) * scale_unit], dtype = numpy.float32)
        simulation_widget.device_world_position = numpy.array([(coordinate_x + 0.5) * scale_unit, 0.2, (coordinate_z + 1.4) * scale_unit], dtype = numpy.float32)

        simulation_widget.yaw_degrees          = 90.0
        simulation_widget.target_yaw_degrees   = 90.0
        simulation_widget.solution_path_points = [(coordinate_x, coordinate_z)]
        simulation_widget.lamp_world_positions = []

        for lamp_x in range(minimum_bound + 2, maximum_bound - 2, 4):
            for lamp_z in range(minimum_bound + 2, maximum_bound - 2, 4):
                simulation_widget.lamp_world_positions.append(((lamp_x + 0.5) * scale_unit, (lamp_z + 0.5) * scale_unit))

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        simulation_widget.madness_ratio = min(1.0, simulation_widget.elapsed_time_seconds * 0.015)

        if simulation_widget.elapsed_time_seconds <= 45.0:
            return

        simulation_widget.finale_sequence_active = True
        simulation_widget.finale_timer_seconds  += delta_time_seconds
        simulation_widget.heavy_eyelids_factor   = min(1.0, simulation_widget.finale_timer_seconds / 7.0)
        simulation_widget.camera_position[1]     = max(0.20, simulation_widget.camera_position[1] - delta_time_seconds * 0.22)
        simulation_widget.target_pitch_degrees   = min(40.0, simulation_widget.target_pitch_degrees + delta_time_seconds * 8.0)

        if simulation_widget.finale_timer_seconds > 3.0 and simulation_widget.finale_timer_seconds - delta_time_seconds <= 3.0:
            simulation_widget.display_message(Constants.FATE_TEXTS["burnout_lay_down"])

        if simulation_widget.finale_timer_seconds >= 8.5:
            simulation_widget.finalize_easter_egg_termination(Constants.FATE_TEXTS["burnout_termination"])

    def get_radar_status_text(self, simulation_widget: object) -> str:
        return Constants.FATE_TEXTS["burnout_no_exit"]


class GravityFate(FateScenario):
    name: str = "GRAVITY"

    def __init__(self) -> None:
        self.destruction_started: bool  = False
        self.destruction_timer:   float = 0.0

    def setup_world(self, simulation_widget: object) -> None:
        simulation_widget.gravity_tilt = 10.0

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        total_waypoints = len(simulation_widget.solution_path_points)
        path_progress   = (
            float(simulation_widget.current_waypoint_index) / float(max(1, total_waypoints))
            if simulation_widget.solution_path_points
            else 0.0
        )

        decay_intensity = max(0.0, (path_progress - 0.5) * 2.0)
        maximum_tilt    = 16.0 + decay_intensity * 26.0
        elapsed_seconds = simulation_widget.elapsed_time_seconds

        smooth_roll_tilt = (
            math.sin(elapsed_seconds * 0.42) * maximum_tilt +
            math.cos(elapsed_seconds * 0.21) * (maximum_tilt * 0.45)
        )

        simulation_widget.gravity_tilt = smooth_roll_tilt

        simulation_widget.target_pitch_degrees += (
            math.sin(elapsed_seconds * 0.28) * 0.35 * delta_time_seconds * 8.0
        )

        forward_horizontal = numpy.array([simulation_widget.camera_front[0], 0.0, simulation_widget.camera_front[2]], dtype = numpy.float32)
        forward_magnitude  = numpy.linalg.norm(forward_horizontal)

        if forward_magnitude > 1e-4:
            forward_horizontal /= forward_magnitude

        right_horizontal = numpy.cross(forward_horizontal, simulation_widget.camera_up)
        right_magnitude  = numpy.linalg.norm(right_horizontal)

        if right_magnitude > 1e-4:
            right_horizontal /= right_magnitude

        tilt_radians        = math.radians(smooth_roll_tilt)
        sliding_step_vector = right_horizontal * math.sin(tilt_radians) * (1.2 + decay_intensity * 1.8) * delta_time_seconds

        candidate_slide_x = simulation_widget.camera_position[0] + sliding_step_vector[0]

        if not WorldBuilder.check_tile_collision(candidate_slide_x, simulation_widget.camera_position[2], 0.35, simulation_widget.world_grid_array, simulation_widget.cell_scale_units, simulation_widget.maze_dimension):
            simulation_widget.camera_position[0] = candidate_slide_x

        candidate_slide_z = simulation_widget.camera_position[2] + sliding_step_vector[2]

        if not WorldBuilder.check_tile_collision(simulation_widget.camera_position[0], candidate_slide_z, 0.35, simulation_widget.world_grid_array, simulation_widget.cell_scale_units, simulation_widget.maze_dimension):
            simulation_widget.camera_position[2] = candidate_slide_z

        if path_progress >= 0.5:
            if not self.destruction_started:
                self.destruction_started = True
                simulation_widget.display_message(Constants.FATE_TEXTS["gravity_anomaly"])
                Player.ui_player.play_sound(".vault/Anomaly/PaintingCrash", volume = 0.8)

            self.destruction_timer -= delta_time_seconds

            if self.destruction_timer <= 0.0:
                self.destruction_timer = max(0.28, 0.75 - decay_intensity * 0.40)

                player_cell_x = int(simulation_widget.camera_position[0] / simulation_widget.cell_scale_units)
                player_cell_z = int(simulation_widget.camera_position[2] / simulation_widget.cell_scale_units)
                search_radius = 4 + int(decay_intensity * 4)

                candidate_walls = []

                for offset_x in range(-search_radius, search_radius + 1):
                    for offset_z in range(-search_radius, search_radius + 1):
                        grid_x = player_cell_x + offset_x
                        grid_z = player_cell_z + offset_z

                        if 1 <= grid_x < simulation_widget.maze_dimension - 1 and 1 <= grid_z < simulation_widget.maze_dimension - 1:
                            if simulation_widget.world_grid_array[grid_x, grid_z] == 1:
                                candidate_walls.append((grid_x, grid_z))

                if candidate_walls:
                    target_wall_x, target_wall_z = random.choice(candidate_walls)
                    simulation_widget.world_grid_array[target_wall_x, target_wall_z] = 0

                    simulation_widget.wall_renderer.build_monolithic_maze_mesh(
                        simulation_widget.cell_scale_units,
                        simulation_widget.maze_dimension,
                        simulation_widget.wall_height_units,
                        simulation_widget.world_grid_array,
                        floor_active = True
                    )

                    destruction_pan = simulation_widget.calculate_audio_pan(
                        target_wall_x * simulation_widget.cell_scale_units,
                        target_wall_z * simulation_widget.cell_scale_units
                    )
                    Player.ui_player.play_sound(".vault/Anomaly/SparkPop", volume = 0.65, pan = destruction_pan)

                    for lamp in simulation_widget.lamp_renderer.lamps_list:
                        if not lamp.is_broken:
                            distance_to_lamp = math.hypot(
                                lamp.position_x - simulation_widget.camera_position[0],
                                lamp.position_z - simulation_widget.camera_position[2]
                            )

                            if distance_to_lamp < search_radius * simulation_widget.cell_scale_units and random.random() < 0.20:
                                lamp.is_broken      = True
                                lamp.flicker_factor = 0.0
                                lamp.spawn_burst_sparks(simulation_widget.wall_height_units - 0.09)
                                simulation_widget.lamp_renderer.tubes_need_rebuild = True

                    simulation_widget.reality_tear_ratio      = min(0.85, simulation_widget.reality_tear_ratio + 0.06 * decay_intensity)
                    simulation_widget.emergency_red_intensity = min(0.70, decay_intensity * 0.65)

        terminal_point       = simulation_widget.solution_path_points[-1]
        distance_to_terminal = math.hypot(
            simulation_widget.camera_position[0] - (terminal_point[0] + 0.5) * simulation_widget.cell_scale_units,
            simulation_widget.camera_position[2] - (terminal_point[1] + 0.5) * simulation_widget.cell_scale_units
        )

        has_reached_abyss = distance_to_terminal < 4.2 or path_progress >= 0.96

        if has_reached_abyss and not simulation_widget.finale_sequence_active:
            simulation_widget.finale_sequence_active = True
            simulation_widget.display_message(Constants.FATE_TEXTS["gravity_zero"])
            Player.ui_player.play_sound(".vault/Anomaly/PaintingCrash", volume = 1.0)
            Player.ui_player.play_sound(".vault/Anomaly/SparkPop", volume = 0.9)

            simulation_widget.wall_renderer.build_monolithic_maze_mesh(
                simulation_widget.cell_scale_units,
                simulation_widget.maze_dimension,
                simulation_widget.wall_height_units,
                simulation_widget.world_grid_array,
                floor_active = False
            )

        if not simulation_widget.finale_sequence_active:
            return

        simulation_widget.finale_timer_seconds += delta_time_seconds
        simulation_widget.cut_to_black_factor   = min(1.0, simulation_widget.finale_timer_seconds / 4.5)
        simulation_widget.camera_position[1]    = max(-25.0, simulation_widget.camera_position[1] - delta_time_seconds * 2.8)
        simulation_widget.gravity_tilt         += delta_time_seconds * 28.0

        if simulation_widget.finale_timer_seconds >= 4.5:
            simulation_widget.finalize_easter_egg_termination(Constants.FATE_TEXTS["gravity_termination"])

    def get_radar_status_text(self, simulation_widget: object) -> str:
        if simulation_widget.finale_sequence_active:
            return Constants.FATE_TEXTS["gravity_void_status"]

        total_waypoints = len(simulation_widget.solution_path_points)
        path_progress   = (
            float(simulation_widget.current_waypoint_index) / float(max(1, total_waypoints))
            if simulation_widget.solution_path_points
            else 0.0
        )

        current_tilt_degrees = int(abs(simulation_widget.gravity_tilt))

        if path_progress >= 0.5:
            decay_percentage = int((path_progress - 0.5) * 200.0)
            return Constants.FATE_TEXTS["gravity_decay_status"].format(
                decay = decay_percentage,
                tilt  = current_tilt_degrees
            )

        return Constants.FATE_TEXTS["gravity_tilt_status"].format(tilt = current_tilt_degrees)


class RadarGlitchFate(FateScenario):
    name: str = "RADAR_GLITCH"

    def setup_world(self, simulation_widget: object) -> None:
        chosen_point                              = simulation_widget.choose_random_floor_coordinate(10.0)
        simulation_widget.bogus_waypoint_position = numpy.array(chosen_point, dtype = numpy.float32)
        simulation_widget.radar_chase_count       = 0

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        if not simulation_widget.device_picked_up:
            return

        if simulation_widget.finale_sequence_active:
            simulation_widget.finale_timer_seconds += delta_time_seconds
            simulation_widget.cut_to_black_factor   = min(1.0, simulation_widget.finale_timer_seconds / 4.0)

            if simulation_widget.finale_timer_seconds >= 4.0:
                simulation_widget.finalize_easter_egg_termination(Constants.FATE_TEXTS["radar_glitch_termination"])

            return

        distance_to_bogus = math.hypot(
            simulation_widget.camera_position[0] - simulation_widget.bogus_waypoint_position[0],
            simulation_widget.camera_position[2] - simulation_widget.bogus_waypoint_position[1]
        )

        if distance_to_bogus < 2.5:
            simulation_widget.radar_chase_count += 1
            Player.ui_player.play_sound(".vault/Anomaly/RadarBeep", volume = 0.35)

            if simulation_widget.radar_chase_count < 4:
                next_signal_number = simulation_widget.radar_chase_count + 1
                simulation_widget.display_message(
                    Constants.FATE_TEXTS["radar_bounce"].format(number = next_signal_number)
                )
                new_floor_coordinate                      = simulation_widget.choose_random_floor_coordinate(10.0)
                simulation_widget.bogus_waypoint_position = numpy.array(new_floor_coordinate, dtype = numpy.float32)

            else:
                simulation_widget.display_message(Constants.FATE_TEXTS["radar_dissolved"])
                simulation_widget.finale_sequence_active = True

    def get_radar_status_text(self, simulation_widget: object) -> str:
        if simulation_widget.finale_sequence_active:
            return Constants.FATE_TEXTS["radar_no_carrier"]

        titles  = Constants.RADAR_GLITCH_STATUS_TITLES
        current = titles[int(simulation_widget.elapsed_time_seconds * 2.0) % len(titles)]
        return f"{current} #{simulation_widget.radar_chase_count + 1}"


class SilentHelpFate(FateScenario):
    name: str = "SILENT_HELP"

    def update(
            self,
            simulation_widget:  object,
            delta_time_seconds: float
        ) -> None:

        if not simulation_widget.solution_path_points:
            return

        terminal_node      = simulation_widget.solution_path_points[-1]
        scale_unit         = simulation_widget.cell_scale_units
        distance_to_finish = math.hypot(
            simulation_widget.camera_position[0] - (terminal_node[0] + 0.5) * scale_unit,
            simulation_widget.camera_position[2] - (terminal_node[1] + 0.5) * scale_unit
        )

        should_spawn = (
            distance_to_finish < 3.2 or
            simulation_widget.current_waypoint_index >= len(simulation_widget.solution_path_points) - 1
        )

        if should_spawn and not simulation_widget.sprite_entity_active:
            simulation_widget.spawn_chipsa_behind_player()

        if not simulation_widget.sprite_entity_active:
            return

        if simulation_widget.chipsa_following_state and not simulation_widget.finale_sequence_active:
            simulation_widget.chipsa_follow_timer -= delta_time_seconds
            offset_to_player                       = simulation_widget.camera_position - simulation_widget.sprite_entity_position
            offset_to_player[1]                    = 0.0
            player_distance                        = numpy.linalg.norm(offset_to_player)

            simulation_widget.chipsa_repath_timer -= delta_time_seconds

            if simulation_widget.chipsa_repath_timer <= 0.0:
                simulation_widget.chipsa_repath_timer   = 0.35
                simulation_widget.chipsa_path_waypoints = WorldBuilder.find_shortest_grid_path(
                    simulation_widget.sprite_entity_position,
                    simulation_widget.camera_position,
                    simulation_widget.world_grid_array,
                    simulation_widget.cell_scale_units,
                    simulation_widget.maze_dimension
                )

            if player_distance > 3.2:
                follow_speed = 4.0 if player_distance > 6.0 else 2.5
                simulation_widget.sprite_entity_position = simulation_widget.step_entity_navigation(
                    simulation_widget.sprite_entity_position,
                    simulation_widget.chipsa_path_waypoints,
                    follow_speed,
                    delta_time_seconds
                )

            if simulation_widget.chipsa_follow_timer <= 0.0:
                simulation_widget.finale_sequence_active = True
                simulation_widget.display_message(Constants.FATE_TEXTS["silent_help"])

        if not simulation_widget.finale_sequence_active:
            return

        simulation_widget.finale_timer_seconds += delta_time_seconds
        simulation_widget.cut_to_black_factor   = min(1.0, simulation_widget.finale_timer_seconds / 4.0)

        if simulation_widget.finale_timer_seconds >= 4.0:
            simulation_widget.finalize_easter_egg_termination(Constants.FATE_TEXTS["silent_help"])

# Registry

AVAILABLE_FATE_REGISTRY: dict[str, type[FateScenario]] = {
    "SILENT_HELP":  SilentHelpFate,
    "RADAR_GLITCH": RadarGlitchFate,
    "STANDARD":     StandardFate,
    "GRAVITY":      GravityFate,
    "BURNOUT":      BurnoutFate
}

def create_fate_scenario(scenario_name: str) -> FateScenario:
    scenario_class = AVAILABLE_FATE_REGISTRY.get(scenario_name, StandardFate)
    return scenario_class()