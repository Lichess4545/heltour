(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}else if(typeof define==="function"&&define.amd){define([],f)}else{var g;if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}else if(typeof self!=="undefined"){g=self}else{g=this}g.Chessground = f()}})(function(){var define,module,exports;return (function e(t,n,r){function s(o,u){if(!n[o]){if(!t[o]){var a=typeof require=="function"&&require;if(!u&&a)return a(o,!0);if(i)return i(o,!0);var f=new Error("Cannot find module '"+o+"'");throw f.code="MODULE_NOT_FOUND",f}var l=n[o]={exports:{}};t[o][0].call(l.exports,function(e){var n=t[o][1][e];return s(n?n:e)},l,l.exports,e,t,n,r)}return n[o].exports}var i=typeof require=="function"&&require;for(var o=0;o<r.length;o++)s(r[o]);return s})({1:[function(require,module,exports){
var m = require('mithril');
var ctrl = require('./ctrl');
var view = require('./view');
var api = require('./api');

// for usage outside of mithril
function init(element, config) {

  var controller = new ctrl(config);

  m.render(element, view(controller));

  return api(controller);
}

module.exports = init;
module.exports.controller = ctrl;
module.exports.view = view;
module.exports.fen = require('./fen');
module.exports.util = require('./util');
module.exports.configure = require('./configure');
module.exports.anim = require('./anim');
module.exports.board = require('./board');
module.exports.drag = require('./drag');

},{"./anim":4,"./api":5,"./board":6,"./configure":7,"./ctrl":9,"./drag":11,"./fen":13,"./util":17,"./view":18,"mithril":3}],2:[function(require,module,exports){
/*!
 * @name JavaScript/NodeJS Merge v1.2.0
 * @author yeikos
 * @repository https://github.com/yeikos/js.merge

 * Copyright 2014 yeikos - MIT license
 * https://raw.github.com/yeikos/js.merge/master/LICENSE
 */

;(function(isNode) {

	/**
	 * Merge one or more objects 
	 * @param bool? clone
	 * @param mixed,... arguments
	 * @return object
	 */

	var Public = function(clone) {

		return merge(clone === true, false, arguments);

	}, publicName = 'merge';

	/**
	 * Merge two or more objects recursively 
	 * @param bool? clone
	 * @param mixed,... arguments
	 * @return object
	 */

	Public.recursive = function(clone) {

		return merge(clone === true, true, arguments);

	};

	/**
	 * Clone the input removing any reference
	 * @param mixed input
	 * @return mixed
	 */

	Public.clone = function(input) {

		var output = input,
			type = typeOf(input),
			index, size;

		if (type === 'array') {

			output = [];
			size = input.length;

			for (index=0;index<size;++index)

				output[index] = Public.clone(input[index]);

		} else if (type === 'object') {

			output = {};

			for (index in input)

				output[index] = Public.clone(input[index]);

		}

		return output;

	};

	/**
	 * Merge two objects recursively
	 * @param mixed input
	 * @param mixed extend
	 * @return mixed
	 */

	function merge_recursive(base, extend) {

		if (typeOf(base) !== 'object')

			return extend;

		for (var key in extend) {

			if (typeOf(base[key]) === 'object' && typeOf(extend[key]) === 'object') {

				base[key] = merge_recursive(base[key], extend[key]);

			} else {

				base[key] = extend[key];

			}

		}

		return base;

	}

	/**
	 * Merge two or more objects
	 * @param bool clone
	 * @param bool recursive
	 * @param array argv
	 * @return object
	 */

	function merge(clone, recursive, argv) {

		var result = argv[0],
			size = argv.length;

		if (clone || typeOf(result) !== 'object')

			result = {};

		for (var index=0;index<size;++index) {

			var item = argv[index],

				type = typeOf(item);

			if (type !== 'object') continue;

			for (var key in item) {

				var sitem = clone ? Public.clone(item[key]) : item[key];

				if (recursive) {

					result[key] = merge_recursive(result[key], sitem);

				} else {

					result[key] = sitem;

				}

			}

		}

		return result;

	}

	/**
	 * Get type of variable
	 * @param mixed input
	 * @return string
	 *
	 * @see http://jsperf.com/typeofvar
	 */

	function typeOf(input) {

		return ({}).toString.call(input).slice(8, -1).toLowerCase();

	}

	if (isNode) {

		module.exports = Public;

	} else {

		window[publicName] = Public;

	}

})(typeof module === 'object' && module && typeof module.exports === 'object' && module.exports);
},{}],3:[function(require,module,exports){
var m = (function app(window, undefined) {
	"use strict";
  	var VERSION = "v0.2.1";
	function isFunction(object) {
		return typeof object === "function";
	}
	function isObject(object) {
		return type.call(object) === "[object Object]";
	}
	function isString(object) {
		return type.call(object) === "[object String]";
	}
	var isArray = Array.isArray || function (object) {
		return type.call(object) === "[object Array]";
	};
	var type = {}.toString;
	var parser = /(?:(^|#|\.)([^#\.\[\]]+))|(\[.+?\])/g, attrParser = /\[(.+?)(?:=("|'|)(.*?)\2)?\]/;
	var voidElements = /^(AREA|BASE|BR|COL|COMMAND|EMBED|HR|IMG|INPUT|KEYGEN|LINK|META|PARAM|SOURCE|TRACK|WBR)$/;
	var noop = function () {};

	// caching commonly used variables
	var $document, $location, $requestAnimationFrame, $cancelAnimationFrame;

	// self invoking function needed because of the way mocks work
	function initialize(window) {
		$document = window.document;
		$location = window.location;
		$cancelAnimationFrame = window.cancelAnimationFrame || window.clearTimeout;
		$requestAnimationFrame = window.requestAnimationFrame || window.setTimeout;
	}

	initialize(window);

	m.version = function() {
		return VERSION;
	};

	/**
	 * @typedef {String} Tag
	 * A string that looks like -> div.classname#id[param=one][param2=two]
	 * Which describes a DOM node
	 */

	/**
	 *
	 * @param {Tag} The DOM node tag
	 * @param {Object=[]} optional key-value pairs to be mapped to DOM attrs
	 * @param {...mNode=[]} Zero or more Mithril child nodes. Can be an array, or splat (optional)
	 *
	 */
	function m(tag, pairs) {
		for (var args = [], i = 1; i < arguments.length; i++) {
			args[i - 1] = arguments[i];
		}
		if (isObject(tag)) return parameterize(tag, args);
		var hasAttrs = pairs != null && isObject(pairs) && !("tag" in pairs || "view" in pairs || "subtree" in pairs);
		var attrs = hasAttrs ? pairs : {};
		var classAttrName = "class" in attrs ? "class" : "className";
		var cell = {tag: "div", attrs: {}};
		var match, classes = [];
		if (!isString(tag)) throw new Error("selector in m(selector, attrs, children) should be a string");
		while ((match = parser.exec(tag)) != null) {
			if (match[1] === "" && match[2]) cell.tag = match[2];
			else if (match[1] === "#") cell.attrs.id = match[2];
			else if (match[1] === ".") classes.push(match[2]);
			else if (match[3][0] === "[") {
				var pair = attrParser.exec(match[3]);
				cell.attrs[pair[1]] = pair[3] || (pair[2] ? "" :true);
			}
		}

		var children = hasAttrs ? args.slice(1) : args;
		if (children.length === 1 && isArray(children[0])) {
			cell.children = children[0];
		}
		else {
			cell.children = children;
		}

		for (var attrName in attrs) {
			if (attrs.hasOwnProperty(attrName)) {
				if (attrName === classAttrName && attrs[attrName] != null && attrs[attrName] !== "") {
					classes.push(attrs[attrName]);
					cell.attrs[attrName] = ""; //create key in correct iteration order
				}
				else cell.attrs[attrName] = attrs[attrName];
			}
		}
		if (classes.length) cell.attrs[classAttrName] = classes.join(" ");

		return cell;
	}
	function forEach(list, f) {
		for (var i = 0; i < list.length && !f(list[i], i++);) {}
	}
	function forKeys(list, f) {
		forEach(list, function (attrs, i) {
			return (attrs = attrs && attrs.attrs) && attrs.key != null && f(attrs, i);
		});
	}
	// This function was causing deopts in Chrome.
	// Well no longer
	function dataToString(data) {
    if (data == null) return '';
    if (typeof data === 'object') return data;
    if (data.toString() == null) return ""; // prevent recursion error on FF
    return data;
	}
	// This function was causing deopts in Chrome.
	function injectTextNode(parentElement, first, index, data) {
		try {
			insertNode(parentElement, first, index);
			first.nodeValue = data;
		} catch (e) {} //IE erroneously throws error when appending an empty text node after a null
	}

	function flatten(list) {
		//recursively flatten array
		for (var i = 0; i < list.length; i++) {
			if (isArray(list[i])) {
				list = list.concat.apply([], list);
				//check current index again and flatten until there are no more nested arrays at that index
				i--;
			}
		}
		return list;
	}

	function insertNode(parentElement, node, index) {
		parentElement.insertBefore(node, parentElement.childNodes[index] || null);
	}

	var DELETION = 1, INSERTION = 2, MOVE = 3;

	function handleKeysDiffer(data, existing, cached, parentElement) {
		forKeys(data, function (key, i) {
			existing[key = key.key] = existing[key] ? {
				action: MOVE,
				index: i,
				from: existing[key].index,
				element: cached.nodes[existing[key].index] || $document.createElement("div")
			} : {action: INSERTION, index: i};
		});
		var actions = [];
		for (var prop in existing) actions.push(existing[prop]);
		var changes = actions.sort(sortChanges), newCached = new Array(cached.length);
		newCached.nodes = cached.nodes.slice();

		forEach(changes, function (change) {
			var index = change.index;
			if (change.action === DELETION) {
				clear(cached[index].nodes, cached[index]);
				newCached.splice(index, 1);
			}
			if (change.action === INSERTION) {
				var dummy = $document.createElement("div");
				dummy.key = data[index].attrs.key;
				insertNode(parentElement, dummy, index);
				newCached.splice(index, 0, {
					attrs: {key: data[index].attrs.key},
					nodes: [dummy]
				});
				newCached.nodes[index] = dummy;
			}

			if (change.action === MOVE) {
				var changeElement = change.element;
				var maybeChanged = parentElement.childNodes[index];
				if (maybeChanged !== changeElement && changeElement !== null) {
					parentElement.insertBefore(changeElement, maybeChanged || null);
				}
				newCached[index] = cached[change.from];
				newCached.nodes[index] = changeElement;
			}
		});

		return newCached;
	}

	function diffKeys(data, cached, existing, parentElement) {
		var keysDiffer = data.length !== cached.length;
		if (!keysDiffer) {
			forKeys(data, function (attrs, i) {
				var cachedCell = cached[i];
				return keysDiffer = cachedCell && cachedCell.attrs && cachedCell.attrs.key !== attrs.key;
			});
		}

		return keysDiffer ? handleKeysDiffer(data, existing, cached, parentElement) : cached;
	}

	function diffArray(data, cached, nodes) {
		//diff the array itself

		//update the list of DOM nodes by collecting the nodes from each item
		forEach(data, function (_, i) {
			if (cached[i] != null) nodes.push.apply(nodes, cached[i].nodes);
		})
		//remove items from the end of the array if the new array is shorter than the old one. if errors ever happen here, the issue is most likely
		//a bug in the construction of the `cached` data structure somewhere earlier in the program
		forEach(cached.nodes, function (node, i) {
			if (node.parentNode != null && nodes.indexOf(node) < 0) clear([node], [cached[i]]);
		})
		if (data.length < cached.length) cached.length = data.length;
		cached.nodes = nodes;
	}

	function buildArrayKeys(data) {
		var guid = 0;
		forKeys(data, function () {
			forEach(data, function (attrs) {
				if ((attrs = attrs && attrs.attrs) && attrs.key == null) attrs.key = "__mithril__" + guid++;
			})
			return 1;
		});
	}

	function maybeRecreateObject(data, cached, dataAttrKeys) {
		//if an element is different enough from the one in cache, recreate it
		if (data.tag !== cached.tag ||
				dataAttrKeys.sort().join() !== Object.keys(cached.attrs).sort().join() ||
				data.attrs.id !== cached.attrs.id ||
				data.attrs.key !== cached.attrs.key ||
				(m.redraw.strategy() === "all" && (!cached.configContext || cached.configContext.retain !== true)) ||
				(m.redraw.strategy() === "diff" && cached.configContext && cached.configContext.retain === false)) {
			if (cached.nodes.length) clear(cached.nodes);
			if (cached.configContext && isFunction(cached.configContext.onunload)) cached.configContext.onunload();
			if (cached.controllers) {
				forEach(cached.controllers, function (controller) {
					if (controller.unload) controller.onunload({preventDefault: noop});
				});
			}
		}
	}

	function getObjectNamespace(data, namespace) {
		return data.attrs.xmlns ? data.attrs.xmlns :
			data.tag === "svg" ? "http://www.w3.org/2000/svg" :
			data.tag === "math" ? "http://www.w3.org/1998/Math/MathML" :
			namespace;
	}

	function unloadCachedControllers(cached, views, controllers) {
		if (controllers.length) {
			cached.views = views;
			cached.controllers = controllers;
			forEach(controllers, function (controller) {
				if (controller.onunload && controller.onunload.$old) controller.onunload = controller.onunload.$old;
				if (pendingRequests && controller.onunload) {
					var onunload = controller.onunload;
					controller.onunload = noop;
					controller.onunload.$old = onunload;
				}
			});
		}
	}

	function scheduleConfigsToBeCalled(configs, data, node, isNew, cached) {
		//schedule configs to be called. They are called after `build`
		//finishes running
		if (isFunction(data.attrs.config)) {
			var context = cached.configContext = cached.configContext || {};

			//bind
			configs.push(function() {
				return data.attrs.config.call(data, node, !isNew, context, cached);
			});
		}
	}

	function buildUpdatedNode(cached, data, editable, hasKeys, namespace, views, configs, controllers) {
		var node = cached.nodes[0];
		if (hasKeys) setAttributes(node, data.tag, data.attrs, cached.attrs, namespace);
		cached.children = build(node, data.tag, undefined, undefined, data.children, cached.children, false, 0, data.attrs.contenteditable ? node : editable, namespace, configs);
		cached.nodes.intact = true;

		if (controllers.length) {
			cached.views = views;
			cached.controllers = controllers;
		}

		return node;
	}

	function handleNonexistentNodes(data, parentElement, index) {
		var nodes;
		if (data.$trusted) {
			nodes = injectHTML(parentElement, index, data);
		}
		else {
			nodes = [$document.createTextNode(data)];
			if (!parentElement.nodeName.match(voidElements)) insertNode(parentElement, nodes[0], index);
		}

		var cached = typeof data === "string" || typeof data === "number" || typeof data === "boolean" ? new data.constructor(data) : data;
		cached.nodes = nodes;
		return cached;
	}

	function reattachNodes(data, cached, parentElement, editable, index, parentTag) {
		var nodes = cached.nodes;
		if (!editable || editable !== $document.activeElement) {
			if (data.$trusted) {
				clear(nodes, cached);
				nodes = injectHTML(parentElement, index, data);
			}
			//corner case: replacing the nodeValue of a text node that is a child of a textarea/contenteditable doesn't work
			//we need to update the value property of the parent textarea or the innerHTML of the contenteditable element instead
			else if (parentTag === "textarea") {
				parentElement.value = data;
			}
			else if (editable) {
				editable.innerHTML = data;
			}
			else {
				//was a trusted string
				if (nodes[0].nodeType === 1 || nodes.length > 1) {
					clear(cached.nodes, cached);
					nodes = [$document.createTextNode(data)];
				}
				injectTextNode(parentElement, nodes[0], index, data);
			}
		}
		cached = new data.constructor(data);
		cached.nodes = nodes;
		return cached;
	}

	function handleText(cached, data, index, parentElement, shouldReattach, editable, parentTag) {
		//handle text nodes
		return cached.nodes.length === 0 ? handleNonexistentNodes(data, parentElement, index) :
			cached.valueOf() !== data.valueOf() || shouldReattach === true ?
				reattachNodes(data, cached, parentElement, editable, index, parentTag) :
			(cached.nodes.intact = true, cached);
	}

	function getSubArrayCount(item) {
		if (item.$trusted) {
			//fix offset of next element if item was a trusted string w/ more than one html element
			//the first clause in the regexp matches elements
			//the second clause (after the pipe) matches text nodes
			var match = item.match(/<[^\/]|\>\s*[^<]/g);
			if (match != null) return match.length;
		}
		else if (isArray(item)) {
			return item.length;
		}
		return 1;
	}

	function buildArray(data, cached, parentElement, index, parentTag, shouldReattach, editable, namespace, configs) {
		data = flatten(data);
		var nodes = [], intact = cached.length === data.length, subArrayCount = 0;

		//keys algorithm: sort elements without recreating them if keys are present
		//1) create a map of all existing keys, and mark all for deletion
		//2) add new keys to map and mark them for addition
		//3) if key exists in new list, change action from deletion to a move
		//4) for each key, handle its corresponding action as marked in previous steps
		var existing = {}, shouldMaintainIdentities = false;
		forKeys(cached, function (attrs, i) {
			shouldMaintainIdentities = true;
			existing[cached[i].attrs.key] = {action: DELETION, index: i};
		});

		buildArrayKeys(data);
		if (shouldMaintainIdentities) cached = diffKeys(data, cached, existing, parentElement);
		//end key algorithm

		var cacheCount = 0;
		//faster explicitly written
		for (var i = 0, len = data.length; i < len; i++) {
			//diff each item in the array
			var item = build(parentElement, parentTag, cached, index, data[i], cached[cacheCount], shouldReattach, index + subArrayCount || subArrayCount, editable, namespace, configs);

			if (item !== undefined) {
				intact = intact && item.nodes.intact;
				subArrayCount += getSubArrayCount(item);
				cached[cacheCount++] = item;
			}
		}

		if (!intact) diffArray(data, cached, nodes);
		return cached
	}

	function makeCache(data, cached, index, parentIndex, parentCache) {
		if (cached != null) {
			if (type.call(cached) === type.call(data)) return cached;

			if (parentCache && parentCache.nodes) {
				var offset = index - parentIndex, end = offset + (isArray(data) ? data : cached.nodes).length;
				clear(parentCache.nodes.slice(offset, end), parentCache.slice(offset, end));
			} else if (cached.nodes) {
				clear(cached.nodes, cached);
			}
		}

		cached = new data.constructor();
		//if constructor creates a virtual dom element, use a blank object
		//as the base cached node instead of copying the virtual el (#277)
		if (cached.tag) cached = {};
		cached.nodes = [];
		return cached;
	}

	function constructNode(data, namespace) {
		return namespace === undefined ?
			data.attrs.is ? $document.createElement(data.tag, data.attrs.is) : $document.createElement(data.tag) :
			data.attrs.is ? $document.createElementNS(namespace, data.tag, data.attrs.is) : $document.createElementNS(namespace, data.tag);
	}

	function constructAttrs(data, node, namespace, hasKeys) {
		return hasKeys ? setAttributes(node, data.tag, data.attrs, {}, namespace) : data.attrs;
	}

	function constructChildren(data, node, cached, editable, namespace, configs) {
		return data.children != null && data.children.length > 0 ?
			build(node, data.tag, undefined, undefined, data.children, cached.children, true, 0, data.attrs.contenteditable ? node : editable, namespace, configs) :
			data.children;
	}

	function reconstructCached(data, attrs, children, node, namespace, views, controllers) {
		var cached = {tag: data.tag, attrs: attrs, children: children, nodes: [node]};
		unloadCachedControllers(cached, views, controllers);
		if (cached.children && !cached.children.nodes) cached.children.nodes = [];
		//edge case: setting value on <select> doesn't work before children exist, so set it again after children have been created
		if (data.tag === "select" && "value" in data.attrs) setAttributes(node, data.tag, {value: data.attrs.value}, {}, namespace);
		return cached
	}

	function getController(views, view, cachedControllers, controller) {
		var controllerIndex = m.redraw.strategy() === "diff" && views ? views.indexOf(view) : -1;
		return controllerIndex > -1 ? cachedControllers[controllerIndex] :
			typeof controller === "function" ? new controller() : {};
	}

	function updateLists(views, controllers, view, controller) {
		if (controller.onunload != null) unloaders.push({controller: controller, handler: controller.onunload});
		views.push(view);
		controllers.push(controller);
	}

	function checkView(data, view, cached, cachedControllers, controllers, views) {
		var controller = getController(cached.views, view, cachedControllers, data.controller);
		//Faster to coerce to number and check for NaN
		var key = +(data && data.attrs && data.attrs.key);
		data = pendingRequests === 0 || forcing || cachedControllers && cachedControllers.indexOf(controller) > -1 ? data.view(controller) : {tag: "placeholder"};
		if (data.subtree === "retain") return cached;
		if (key === key) (data.attrs = data.attrs || {}).key = key;
		updateLists(views, controllers, view, controller);
		return data;
	}

	function markViews(data, cached, views, controllers) {
		var cachedControllers = cached && cached.controllers;
		while (data.view != null) data = checkView(data, data.view.$original || data.view, cached, cachedControllers, controllers, views);
		return data;
	}

	function buildObject(data, cached, editable, parentElement, index, shouldReattach, namespace, configs) {
		var views = [], controllers = [];
		data = markViews(data, cached, views, controllers);
		if (!data.tag && controllers.length) throw new Error("Component template must return a virtual element, not an array, string, etc.");
		data.attrs = data.attrs || {};
		cached.attrs = cached.attrs || {};
		var dataAttrKeys = Object.keys(data.attrs);
		var hasKeys = dataAttrKeys.length > ("key" in data.attrs ? 1 : 0);
		maybeRecreateObject(data, cached, dataAttrKeys);
		if (!isString(data.tag)) return;
		var isNew = cached.nodes.length === 0;
		namespace = getObjectNamespace(data, namespace);
		var node;
		if (isNew) {
			node = constructNode(data, namespace);
			//set attributes first, then create children
			var attrs = constructAttrs(data, node, namespace, hasKeys)
			var children = constructChildren(data, node, cached, editable, namespace, configs);
			cached = reconstructCached(data, attrs, children, node, namespace, views, controllers);
		}
		else {
			node = buildUpdatedNode(cached, data, editable, hasKeys, namespace, views, configs, controllers);
		}
		if (isNew || shouldReattach === true && node != null) insertNode(parentElement, node, index);
		//schedule configs to be called. They are called after `build`
		//finishes running
		scheduleConfigsToBeCalled(configs, data, node, isNew, cached);
		return cached
	}

	function build(parentElement, parentTag, parentCache, parentIndex, data, cached, shouldReattach, index, editable, namespace, configs) {
		//`build` is a recursive function that manages creation/diffing/removal
		//of DOM elements based on comparison between `data` and `cached`
		//the diff algorithm can be summarized as this:
		//1 - compare `data` and `cached`
		//2 - if they are different, copy `data` to `cached` and update the DOM
		//    based on what the difference is
		//3 - recursively apply this algorithm for every array and for the
		//    children of every virtual element

		//the `cached` data structure is essentially the same as the previous
		//redraw's `data` data structure, with a few additions:
		//- `cached` always has a property called `nodes`, which is a list of
		//   DOM elements that correspond to the data represented by the
		//   respective virtual element
		//- in order to support attaching `nodes` as a property of `cached`,
		//   `cached` is *always* a non-primitive object, i.e. if the data was
		//   a string, then cached is a String instance. If data was `null` or
		//   `undefined`, cached is `new String("")`
		//- `cached also has a `configContext` property, which is the state
		//   storage object exposed by config(element, isInitialized, context)
		//- when `cached` is an Object, it represents a virtual element; when
		//   it's an Array, it represents a list of elements; when it's a
		//   String, Number or Boolean, it represents a text node

		//`parentElement` is a DOM element used for W3C DOM API calls
		//`parentTag` is only used for handling a corner case for textarea
		//values
		//`parentCache` is used to remove nodes in some multi-node cases
		//`parentIndex` and `index` are used to figure out the offset of nodes.
		//They're artifacts from before arrays started being flattened and are
		//likely refactorable
		//`data` and `cached` are, respectively, the new and old nodes being
		//diffed
		//`shouldReattach` is a flag indicating whether a parent node was
		//recreated (if so, and if this node is reused, then this node must
		//reattach itself to the new parent)
		//`editable` is a flag that indicates whether an ancestor is
		//contenteditable
		//`namespace` indicates the closest HTML namespace as it cascades down
		//from an ancestor
		//`configs` is a list of config functions to run after the topmost
		//`build` call finishes running

		//there's logic that relies on the assumption that null and undefined
		//data are equivalent to empty strings
		//- this prevents lifecycle surprises from procedural helpers that mix
		//  implicit and explicit return statements (e.g.
		//  function foo() {if (cond) return m("div")}
		//- it simplifies diffing code
		data = dataToString(data);
		if (data.subtree === "retain") return cached;
		cached = makeCache(data, cached, index, parentIndex, parentCache);
		return isArray(data) ? buildArray(data, cached, parentElement, index, parentTag, shouldReattach, editable, namespace, configs) :
			data != null && isObject(data) ? buildObject(data, cached, editable, parentElement, index, shouldReattach, namespace, configs) :
			!isFunction(data) ? handleText(cached, data, index, parentElement, shouldReattach, editable, parentTag) :
			cached;
	}
	function sortChanges(a, b) { return a.action - b.action || a.index - b.index; }
	function setAttributes(node, tag, dataAttrs, cachedAttrs, namespace) {
		for (var attrName in dataAttrs) {
			var dataAttr = dataAttrs[attrName];
			var cachedAttr = cachedAttrs[attrName];
			if (!(attrName in cachedAttrs) || (cachedAttr !== dataAttr)) {
				cachedAttrs[attrName] = dataAttr;
				//`config` isn't a real attributes, so ignore it
				if (attrName === "config" || attrName === "key") continue;
				//hook event handlers to the auto-redrawing system
				else if (isFunction(dataAttr) && attrName.slice(0, 2) === "on") {
				node[attrName] = autoredraw(dataAttr, node);
				}
				//handle `style: {...}`
				else if (attrName === "style" && dataAttr != null && isObject(dataAttr)) {
				for (var rule in dataAttr) {
						if (cachedAttr == null || cachedAttr[rule] !== dataAttr[rule]) node.style[rule] = dataAttr[rule];
				}
				for (var rule in cachedAttr) {
						if (!(rule in dataAttr)) node.style[rule] = "";
				}
				}
				//handle SVG
				else if (namespace != null) {
				if (attrName === "href") node.setAttributeNS("http://www.w3.org/1999/xlink", "href", dataAttr);
				else node.setAttribute(attrName === "className" ? "class" : attrName, dataAttr);
				}
				//handle cases that are properties (but ignore cases where we should use setAttribute instead)
				//- list and form are typically used as strings, but are DOM element references in js
				//- when using CSS selectors (e.g. `m("[style='']")`), style is used as a string, but it's an object in js
				else if (attrName in node && attrName !== "list" && attrName !== "style" && attrName !== "form" && attrName !== "type" && attrName !== "width" && attrName !== "height") {
				//#348 don't set the value if not needed otherwise cursor placement breaks in Chrome
				if (tag !== "input" || node[attrName] !== dataAttr) node[attrName] = dataAttr;
				}
				else node.setAttribute(attrName, dataAttr);
			}
			//#348 dataAttr may not be a string, so use loose comparison (double equal) instead of strict (triple equal)
			else if (attrName === "value" && tag === "input" && node.value != dataAttr) {
				node.value = dataAttr;
			}
		}
		return cachedAttrs;
	}
	function clear(nodes, cached) {
		for (var i = nodes.length - 1; i > -1; i--) {
			if (nodes[i] && nodes[i].parentNode) {
				try { nodes[i].parentNode.removeChild(nodes[i]); }
				catch (e) {} //ignore if this fails due to order of events (see http://stackoverflow.com/questions/21926083/failed-to-execute-removechild-on-node)
				cached = [].concat(cached);
				if (cached[i]) unload(cached[i]);
			}
		}
		//release memory if nodes is an array. This check should fail if nodes is a NodeList (see loop above)
		if (nodes.length) nodes.length = 0;
	}
	function unload(cached) {
		if (cached.configContext && isFunction(cached.configContext.onunload)) {
			cached.configContext.onunload();
			cached.configContext.onunload = null;
		}
		if (cached.controllers) {
			forEach(cached.controllers, function (controller) {
				if (isFunction(controller.onunload)) controller.onunload({preventDefault: noop});
			});
		}
		if (cached.children) {
			if (isArray(cached.children)) forEach(cached.children, unload);
			else if (cached.children.tag) unload(cached.children);
		}
	}

	var insertAdjacentBeforeEnd = (function () {
		var rangeStrategy = function (parentElement, data) {
			parentElement.appendChild($document.createRange().createContextualFragment(data));
		};
		var insertAdjacentStrategy = function (parentElement, data) {
			parentElement.insertAdjacentHTML("beforeend", data);
		};

		try {
			$document.createRange().createContextualFragment('x');
			return rangeStrategy;
		} catch (e) {
			return insertAdjacentStrategy;
		}
	})();

	function injectHTML(parentElement, index, data) {
		var nextSibling = parentElement.childNodes[index];
		if (nextSibling) {
			var isElement = nextSibling.nodeType !== 1;
			var placeholder = $document.createElement("span");
			if (isElement) {
				parentElement.insertBefore(placeholder, nextSibling || null);
				placeholder.insertAdjacentHTML("beforebegin", data);
				parentElement.removeChild(placeholder);
			}
			else nextSibling.insertAdjacentHTML("beforebegin", data);
		}
		else insertAdjacentBeforeEnd(parentElement, data);

		var nodes = [];
		while (parentElement.childNodes[index] !== nextSibling) {
			nodes.push(parentElement.childNodes[index]);
			index++;
		}
		return nodes;
	}
	function autoredraw(callback, object) {
		return function(e) {
			e = e || event;
			m.redraw.strategy("diff");
			m.startComputation();
			try { return callback.call(object, e); }
			finally {
				endFirstComputation();
			}
		};
	}

	var html;
	var documentNode = {
		appendChild: function(node) {
			if (html === undefined) html = $document.createElement("html");
			if ($document.documentElement && $document.documentElement !== node) {
				$document.replaceChild(node, $document.documentElement);
			}
			else $document.appendChild(node);
			this.childNodes = $document.childNodes;
		},
		insertBefore: function(node) {
			this.appendChild(node);
		},
		childNodes: []
	};
	var nodeCache = [], cellCache = {};
	m.render = function(root, cell, forceRecreation) {
		var configs = [];
		if (!root) throw new Error("Ensure the DOM element being passed to m.route/m.mount/m.render is not undefined.");
		var id = getCellCacheKey(root);
		var isDocumentRoot = root === $document;
		var node = isDocumentRoot || root === $document.documentElement ? documentNode : root;
		if (isDocumentRoot && cell.tag !== "html") cell = {tag: "html", attrs: {}, children: cell};
		if (cellCache[id] === undefined) clear(node.childNodes);
		if (forceRecreation === true) reset(root);
		cellCache[id] = build(node, null, undefined, undefined, cell, cellCache[id], false, 0, null, undefined, configs);
		forEach(configs, function (config) { config(); });
	};
	function getCellCacheKey(element) {
		var index = nodeCache.indexOf(element);
		return index < 0 ? nodeCache.push(element) - 1 : index;
	}

	m.trust = function(value) {
		value = new String(value);
		value.$trusted = true;
		return value;
	};

	function gettersetter(store) {
		var prop = function() {
			if (arguments.length) store = arguments[0];
			return store;
		};

		prop.toJSON = function() {
			return store;
		};

		return prop;
	}

	m.prop = function (store) {
		//note: using non-strict equality check here because we're checking if store is null OR undefined
		if ((store != null && isObject(store) || isFunction(store)) && isFunction(store.then)) {
			return propify(store);
		}

		return gettersetter(store);
	};

	var roots = [], components = [], controllers = [], lastRedrawId = null, lastRedrawCallTime = 0, computePreRedrawHook = null, computePostRedrawHook = null, topComponent, unloaders = [];
	var FRAME_BUDGET = 16; //60 frames per second = 1 call per 16 ms
	function parameterize(component, args) {
		var controller = function() {
			return (component.controller || noop).apply(this, args) || this;
		};
		if (component.controller) controller.prototype = component.controller.prototype;
		var view = function(ctrl) {
			var currentArgs = arguments.length > 1 ? args.concat([].slice.call(arguments, 1)) : args;
			return component.view.apply(component, currentArgs ? [ctrl].concat(currentArgs) : [ctrl]);
		};
		view.$original = component.view;
		var output = {controller: controller, view: view};
		if (args[0] && args[0].key != null) output.attrs = {key: args[0].key};
		return output;
	}
	m.component = function(component) {
		for (var args = [], i = 1; i < arguments.length; i++) args.push(arguments[i]);
		return parameterize(component, args);
	};
	m.mount = m.module = function(root, component) {
		if (!root) throw new Error("Please ensure the DOM element exists before rendering a template into it.");
		var index = roots.indexOf(root);
		if (index < 0) index = roots.length;

		var isPrevented = false;
		var event = {preventDefault: function() {
			isPrevented = true;
			computePreRedrawHook = computePostRedrawHook = null;
		}};

		forEach(unloaders, function (unloader) {
			unloader.handler.call(unloader.controller, event);
			unloader.controller.onunload = null;
		});

		if (isPrevented) {
			forEach(unloaders, function (unloader) {
				unloader.controller.onunload = unloader.handler;
			});
		}
		else unloaders = [];

		if (controllers[index] && isFunction(controllers[index].onunload)) {
			controllers[index].onunload(event);
		}

		var isNullComponent = component === null;

		if (!isPrevented) {
			m.redraw.strategy("all");
			m.startComputation();
			roots[index] = root;
			var currentComponent = component ? (topComponent = component) : (topComponent = component = {controller: noop});
			var controller = new (component.controller || noop)();
			//controllers may call m.mount recursively (via m.route redirects, for example)
			//this conditional ensures only the last recursive m.mount call is applied
			if (currentComponent === topComponent) {
				controllers[index] = controller;
				components[index] = component;
			}
			endFirstComputation();
			if (isNullComponent) {
				removeRootElement(root, index);
			}
			return controllers[index];
		}
		if (isNullComponent) {
			removeRootElement(root, index);
		}
	};

	function removeRootElement(root, index) {
		roots.splice(index, 1);
		controllers.splice(index, 1);
		components.splice(index, 1);
		reset(root);
		nodeCache.splice(getCellCacheKey(root), 1);
	}

	var redrawing = false, forcing = false;
	m.redraw = function(force) {
		if (redrawing) return;
		redrawing = true;
		if (force) forcing = true;
		try {
			//lastRedrawId is a positive number if a second redraw is requested before the next animation frame
			//lastRedrawID is null if it's the first redraw and not an event handler
			if (lastRedrawId && !force) {
				//when setTimeout: only reschedule redraw if time between now and previous redraw is bigger than a frame, otherwise keep currently scheduled timeout
				//when rAF: always reschedule redraw
				if ($requestAnimationFrame === window.requestAnimationFrame || new Date - lastRedrawCallTime > FRAME_BUDGET) {
					if (lastRedrawId > 0) $cancelAnimationFrame(lastRedrawId);
					lastRedrawId = $requestAnimationFrame(redraw, FRAME_BUDGET);
				}
			}
			else {
				redraw();
				lastRedrawId = $requestAnimationFrame(function() { lastRedrawId = null; }, FRAME_BUDGET);
			}
		}
		finally {
			redrawing = forcing = false;
		}
	};
	m.redraw.strategy = m.prop();
	function redraw() {
		if (computePreRedrawHook) {
			computePreRedrawHook();
			computePreRedrawHook = null;
		}
		forEach(roots, function (root, i) {
			var component = components[i];
			if (controllers[i]) {
				var args = [controllers[i]];
				m.render(root, component.view ? component.view(controllers[i], args) : "");
			}
		});
		//after rendering within a routed context, we need to scroll back to the top, and fetch the document title for history.pushState
		if (computePostRedrawHook) {
			computePostRedrawHook();
			computePostRedrawHook = null;
		}
		lastRedrawId = null;
		lastRedrawCallTime = new Date;
		m.redraw.strategy("diff");
	}

	var pendingRequests = 0;
	m.startComputation = function() { pendingRequests++; };
	m.endComputation = function() {
		if (pendingRequests > 1) pendingRequests--;
		else {
			pendingRequests = 0;
			m.redraw();
		}
	}

	function endFirstComputation() {
		if (m.redraw.strategy() === "none") {
			pendingRequests--;
			m.redraw.strategy("diff");
		}
		else m.endComputation();
	}

	m.withAttr = function(prop, withAttrCallback, callbackThis) {
		return function(e) {
			e = e || event;
			var currentTarget = e.currentTarget || this;
			var _this = callbackThis || this;
			withAttrCallback.call(_this, prop in currentTarget ? currentTarget[prop] : currentTarget.getAttribute(prop));
		};
	};

	//routing
	var modes = {pathname: "", hash: "#", search: "?"};
	var redirect = noop, routeParams, currentRoute, isDefaultRoute = false;
	m.route = function(root, arg1, arg2, vdom) {
		//m.route()
		if (arguments.length === 0) return currentRoute;
		//m.route(el, defaultRoute, routes)
		else if (arguments.length === 3 && isString(arg1)) {
			redirect = function(source) {
				var path = currentRoute = normalizeRoute(source);
				if (!routeByValue(root, arg2, path)) {
					if (isDefaultRoute) throw new Error("Ensure the default route matches one of the routes defined in m.route");
					isDefaultRoute = true;
					m.route(arg1, true);
					isDefaultRoute = false;
				}
			};
			var listener = m.route.mode === "hash" ? "onhashchange" : "onpopstate";
			window[listener] = function() {
				var path = $location[m.route.mode];
				if (m.route.mode === "pathname") path += $location.search;
				if (currentRoute !== normalizeRoute(path)) redirect(path);
			};

			computePreRedrawHook = setScroll;
			window[listener]();
		}
		//config: m.route
		else if (root.addEventListener || root.attachEvent) {
			root.href = (m.route.mode !== 'pathname' ? $location.pathname : '') + modes[m.route.mode] + vdom.attrs.href;
			if (root.addEventListener) {
				root.removeEventListener("click", routeUnobtrusive);
				root.addEventListener("click", routeUnobtrusive);
			}
			else {
				root.detachEvent("onclick", routeUnobtrusive);
				root.attachEvent("onclick", routeUnobtrusive);
			}
		}
		//m.route(route, params, shouldReplaceHistoryEntry)
		else if (isString(root)) {
			var oldRoute = currentRoute;
			currentRoute = root;
			var args = arg1 || {};
			var queryIndex = currentRoute.indexOf("?");
			var params = queryIndex > -1 ? parseQueryString(currentRoute.slice(queryIndex + 1)) : {};
			for (var i in args) params[i] = args[i];
			var querystring = buildQueryString(params);
			var currentPath = queryIndex > -1 ? currentRoute.slice(0, queryIndex) : currentRoute;
			if (querystring) currentRoute = currentPath + (currentPath.indexOf("?") === -1 ? "?" : "&") + querystring;

			var shouldReplaceHistoryEntry = (arguments.length === 3 ? arg2 : arg1) === true || oldRoute === root;

			if (window.history.pushState) {
				computePreRedrawHook = setScroll;
				computePostRedrawHook = function() {
					window.history[shouldReplaceHistoryEntry ? "replaceState" : "pushState"](null, $document.title, modes[m.route.mode] + currentRoute);
				};
				redirect(modes[m.route.mode] + currentRoute);
			}
			else {
				$location[m.route.mode] = currentRoute;
				redirect(modes[m.route.mode] + currentRoute);
			}
		}
	};
	m.route.param = function(key) {
		if (!routeParams) throw new Error("You must call m.route(element, defaultRoute, routes) before calling m.route.param()");
		if( !key ){
			return routeParams;
		}
		return routeParams[key];
	};
	m.route.mode = "search";
	function normalizeRoute(route) {
		return route.slice(modes[m.route.mode].length);
	}
	function routeByValue(root, router, path) {
		routeParams = {};

		var queryStart = path.indexOf("?");
		if (queryStart !== -1) {
			routeParams = parseQueryString(path.substr(queryStart + 1, path.length));
			path = path.substr(0, queryStart);
		}

		// Get all routes and check if there's
		// an exact match for the current path
		var keys = Object.keys(router);
		var index = keys.indexOf(path);
		if(index !== -1){
			m.mount(root, router[keys [index]]);
			return true;
		}

		for (var route in router) {
			if (route === path) {
				m.mount(root, router[route]);
				return true;
			}

			var matcher = new RegExp("^" + route.replace(/:[^\/]+?\.{3}/g, "(.*?)").replace(/:[^\/]+/g, "([^\\/]+)") + "\/?$");

			if (matcher.test(path)) {
				path.replace(matcher, function() {
					var keys = route.match(/:[^\/]+/g) || [];
					var values = [].slice.call(arguments, 1, -2);
					forEach(keys, function (key, i) {
						routeParams[key.replace(/:|\./g, "")] = decodeURIComponent(values[i]);
					})
					m.mount(root, router[route]);
				});
				return true;
			}
		}
	}
	function routeUnobtrusive(e) {
		e = e || event;

		if (e.ctrlKey || e.metaKey || e.which === 2) return;

		if (e.preventDefault) e.preventDefault();
		else e.returnValue = false;

		var currentTarget = e.currentTarget || e.srcElement;
		var args = m.route.mode === "pathname" && currentTarget.search ? parseQueryString(currentTarget.search.slice(1)) : {};
		while (currentTarget && currentTarget.nodeName.toUpperCase() !== "A") currentTarget = currentTarget.parentNode;
		m.route(currentTarget[m.route.mode].slice(modes[m.route.mode].length), args);
	}
	function setScroll() {
		if (m.route.mode !== "hash" && $location.hash) $location.hash = $location.hash;
		else window.scrollTo(0, 0);
	}
	function buildQueryString(object, prefix) {
		var duplicates = {};
		var str = [];
		for (var prop in object) {
			var key = prefix ? prefix + "[" + prop + "]" : prop;
			var value = object[prop];

			if (value === null) {
				str.push(encodeURIComponent(key));
			} else if (isObject(value)) {
				str.push(buildQueryString(value, key));
			} else if (isArray(value)) {
				var keys = [];
				duplicates[key] = duplicates[key] || {};
				forEach(value, function (item) {
					if (!duplicates[key][item]) {
						duplicates[key][item] = true;
						keys.push(encodeURIComponent(key) + "=" + encodeURIComponent(item));
					}
				});
				str.push(keys.join("&"));
			} else if (value !== undefined) {
				str.push(encodeURIComponent(key) + "=" + encodeURIComponent(value));
			}
		}
		return str.join("&");
	}
	function parseQueryString(str) {
		if (str === "" || str == null) return {};
		if (str.charAt(0) === "?") str = str.slice(1);

		var pairs = str.split("&"), params = {};
		forEach(pairs, function (string) {
			var pair = string.split("=");
			var key = decodeURIComponent(pair[0]);
			var value = pair.length === 2 ? decodeURIComponent(pair[1]) : null;
			if (params[key] != null) {
				if (!isArray(params[key])) params[key] = [params[key]];
				params[key].push(value);
			}
			else params[key] = value;
		});

		return params;
	}
	m.route.buildQueryString = buildQueryString;
	m.route.parseQueryString = parseQueryString;

	function reset(root) {
		var cacheKey = getCellCacheKey(root);
		clear(root.childNodes, cellCache[cacheKey]);
		cellCache[cacheKey] = undefined;
	}

	m.deferred = function () {
		var deferred = new Deferred();
		deferred.promise = propify(deferred.promise);
		return deferred;
	};
	function propify(promise, initialValue) {
		var prop = m.prop(initialValue);
		promise.then(prop);
		prop.then = function(resolve, reject) {
			return propify(promise.then(resolve, reject), initialValue);
		};
		prop["catch"] = prop.then.bind(null, null);
		prop["finally"] = function(callback) {
			var _callback = function() {return m.deferred().resolve(callback()).promise;};
			return prop.then(function(value) {
				return propify(_callback().then(function() {return value;}), initialValue);
			}, function(reason) {
				return propify(_callback().then(function() {throw new Error(reason);}), initialValue);
			});
		};
		return prop;
	}
	//Promiz.mithril.js | Zolmeister | MIT
	//a modified version of Promiz.js, which does not conform to Promises/A+ for two reasons:
	//1) `then` callbacks are called synchronously (because setTimeout is too slow, and the setImmediate polyfill is too big
	//2) throwing subclasses of Error cause the error to be bubbled up instead of triggering rejection (because the spec does not account for the important use case of default browser error handling, i.e. message w/ line number)
	function Deferred(successCallback, failureCallback) {
		var RESOLVING = 1, REJECTING = 2, RESOLVED = 3, REJECTED = 4;
		var self = this, state = 0, promiseValue = 0, next = [];

		self.promise = {};

		self.resolve = function(value) {
			if (!state) {
				promiseValue = value;
				state = RESOLVING;

				fire();
			}
			return this;
		};

		self.reject = function(value) {
			if (!state) {
				promiseValue = value;
				state = REJECTING;

				fire();
			}
			return this;
		};

		self.promise.then = function(successCallback, failureCallback) {
			var deferred = new Deferred(successCallback, failureCallback)
			if (state === RESOLVED) {
				deferred.resolve(promiseValue);
			}
			else if (state === REJECTED) {
				deferred.reject(promiseValue);
			}
			else {
				next.push(deferred);
			}
			return deferred.promise
		};

		function finish(type) {
			state = type || REJECTED;
			next.map(function(deferred) {
				state === RESOLVED ? deferred.resolve(promiseValue) : deferred.reject(promiseValue);
			});
		}

		function thennable(then, successCallback, failureCallback, notThennableCallback) {
			if (((promiseValue != null && isObject(promiseValue)) || isFunction(promiseValue)) && isFunction(then)) {
				try {
					// count protects against abuse calls from spec checker
					var count = 0;
					then.call(promiseValue, function(value) {
						if (count++) return;
						promiseValue = value;
						successCallback();
					}, function (value) {
						if (count++) return;
						promiseValue = value;
						failureCallback();
					});
				}
				catch (e) {
					m.deferred.onerror(e);
					promiseValue = e;
					failureCallback();
				}
			} else {
				notThennableCallback();
			}
		}

		function fire() {
			// check if it's a thenable
			var then;
			try {
				then = promiseValue && promiseValue.then;
			}
			catch (e) {
				m.deferred.onerror(e);
				promiseValue = e;
				state = REJECTING;
				return fire();
			}

			thennable(then, function() {
				state = RESOLVING;
				fire();
			}, function() {
				state = REJECTING;
				fire();
			}, function() {
				try {
					if (state === RESOLVING && isFunction(successCallback)) {
						promiseValue = successCallback(promiseValue);
					}
					else if (state === REJECTING && isFunction(failureCallback)) {
						promiseValue = failureCallback(promiseValue);
						state = RESOLVING;
					}
				}
				catch (e) {
					m.deferred.onerror(e);
					promiseValue = e;
					return finish();
				}

				if (promiseValue === self) {
					promiseValue = TypeError();
					finish();
				} else {
					thennable(then, function () {
						finish(RESOLVED);
					}, finish, function () {
						finish(state === RESOLVING && RESOLVED);
					});
				}
			});
		}
	}
	m.deferred.onerror = function(e) {
		if (type.call(e) === "[object Error]" && !e.constructor.toString().match(/ Error/)) {
			pendingRequests = 0;
			throw e;
		}
	};

	m.sync = function(args) {
		var method = "resolve";

		function synchronizer(pos, resolved) {
			return function(value) {
				results[pos] = value;
				if (!resolved) method = "reject";
				if (--outstanding === 0) {
					deferred.promise(results);
					deferred[method](results);
				}
				return value;
			};
		}

		var deferred = m.deferred();
		var outstanding = args.length;
		var results = new Array(outstanding);
		if (args.length > 0) {
			forEach(args, function (arg, i) {
				arg.then(synchronizer(i, true), synchronizer(i, false));
			});
		}
		else deferred.resolve([]);

		return deferred.promise;
	};
	function identity(value) { return value; }

	function ajax(options) {
		if (options.dataType && options.dataType.toLowerCase() === "jsonp") {
			var callbackKey = "mithril_callback_" + new Date().getTime() + "_" + (Math.round(Math.random() * 1e16)).toString(36)
			var script = $document.createElement("script");

			window[callbackKey] = function(resp) {
				script.parentNode.removeChild(script);
				options.onload({
					type: "load",
					target: {
						responseText: resp
					}
				});
				window[callbackKey] = undefined;
			};

			script.onerror = function() {
				script.parentNode.removeChild(script);

				options.onerror({
					type: "error",
					target: {
						status: 500,
						responseText: JSON.stringify({
							error: "Error making jsonp request"
						})
					}
				});
				window[callbackKey] = undefined;

				return false;
			}

			script.onload = function() {
				return false;
			};

			script.src = options.url
				+ (options.url.indexOf("?") > 0 ? "&" : "?")
				+ (options.callbackKey ? options.callbackKey : "callback")
				+ "=" + callbackKey
				+ "&" + buildQueryString(options.data || {});
			$document.body.appendChild(script);
		}
		else {
			var xhr = new window.XMLHttpRequest();
			xhr.open(options.method, options.url, true, options.user, options.password);
			xhr.onreadystatechange = function() {
				if (xhr.readyState === 4) {
					if (xhr.status >= 200 && xhr.status < 300) options.onload({type: "load", target: xhr});
					else options.onerror({type: "error", target: xhr});
				}
			};
			if (options.serialize === JSON.stringify && options.data && options.method !== "GET") {
				xhr.setRequestHeader("Content-Type", "application/json; charset=utf-8");
			}
			if (options.deserialize === JSON.parse) {
				xhr.setRequestHeader("Accept", "application/json, text/*");
			}
			if (isFunction(options.config)) {
				var maybeXhr = options.config(xhr, options);
				if (maybeXhr != null) xhr = maybeXhr;
			}

			var data = options.method === "GET" || !options.data ? "" : options.data;
			if (data && (!isString(data) && data.constructor !== window.FormData)) {
				throw new Error("Request data should be either be a string or FormData. Check the `serialize` option in `m.request`");
			}
			xhr.send(data);
			return xhr;
		}
	}

	function bindData(xhrOptions, data, serialize) {
		if (xhrOptions.method === "GET" && xhrOptions.dataType !== "jsonp") {
			var prefix = xhrOptions.url.indexOf("?") < 0 ? "?" : "&";
			var querystring = buildQueryString(data);
			xhrOptions.url = xhrOptions.url + (querystring ? prefix + querystring : "");
		}
		else xhrOptions.data = serialize(data);
		return xhrOptions;
	}

	function parameterizeUrl(url, data) {
		var tokens = url.match(/:[a-z]\w+/gi);
		if (tokens && data) {
			forEach(tokens, function (token) {
				var key = token.slice(1);
				url = url.replace(token, data[key]);
				delete data[key];
			});
		}
		return url;
	}

	m.request = function(xhrOptions) {
		if (xhrOptions.background !== true) m.startComputation();
		var deferred = new Deferred();
		var isJSONP = xhrOptions.dataType && xhrOptions.dataType.toLowerCase() === "jsonp"
		var serialize = xhrOptions.serialize = isJSONP ? identity : xhrOptions.serialize || JSON.stringify;
		var deserialize = xhrOptions.deserialize = isJSONP ? identity : xhrOptions.deserialize || JSON.parse;
		var extract = isJSONP ? function(jsonp) { return jsonp.responseText } : xhrOptions.extract || function(xhr) {
			if (xhr.responseText.length === 0 && deserialize === JSON.parse) {
				return null
			} else {
				return xhr.responseText
			}
		};
		xhrOptions.method = (xhrOptions.method || "GET").toUpperCase();
		xhrOptions.url = parameterizeUrl(xhrOptions.url, xhrOptions.data);
		xhrOptions = bindData(xhrOptions, xhrOptions.data, serialize);
		xhrOptions.onload = xhrOptions.onerror = function(e) {
			try {
				e = e || event;
				var unwrap = (e.type === "load" ? xhrOptions.unwrapSuccess : xhrOptions.unwrapError) || identity;
				var response = unwrap(deserialize(extract(e.target, xhrOptions)), e.target);
				if (e.type === "load") {
					if (isArray(response) && xhrOptions.type) {
						forEach(response, function (res, i) {
							response[i] = new xhrOptions.type(res);
						});
					} else if (xhrOptions.type) {
						response = new xhrOptions.type(response);
					}
				}

				deferred[e.type === "load" ? "resolve" : "reject"](response);
			} catch (e) {
				m.deferred.onerror(e);
				deferred.reject(e);
			}

			if (xhrOptions.background !== true) m.endComputation()
		}

		ajax(xhrOptions);
		deferred.promise = propify(deferred.promise, xhrOptions.initialValue);
		return deferred.promise;
	};

	//testing API
	m.deps = function(mock) {
		initialize(window = mock || window);
		return window;
	};
	//for internal testing only, do not use `m.deps.factory`
	m.deps.factory = app;

	return m;
})(typeof window !== "undefined" ? window : {});

if (typeof module === "object" && module != null && module.exports) module.exports = m;
else if (typeof define === "function" && define.amd) define(function() { return m });

},{}],4:[function(require,module,exports){
var util = require('./util');

// https://gist.github.com/gre/1650294
var easing = {
  easeInOutCubic: function(t) {
    return t < 0.5 ? 4 * t * t * t : (t - 1) * (2 * t - 2) * (2 * t - 2) + 1;
  },
};

function makePiece(k, piece, invert) {
  var key = invert ? util.invertKey(k) : k;
  return {
    key: key,
    pos: util.key2pos(key),
    role: piece.role,
    color: piece.color
  };
}

function samePiece(p1, p2) {
  return p1.role === p2.role && p1.color === p2.color;
}

function closer(piece, pieces) {
  return pieces.sort(function(p1, p2) {
    return util.distance(piece.pos, p1.pos) - util.distance(piece.pos, p2.pos);
  })[0];
}

function computePlan(prev, current) {
  var bounds = current.bounds(),
    width = bounds.width / 8,
    height = bounds.height / 8,
    anims = {},
    animedOrigs = [],
    fadings = [],
    missings = [],
    news = [],
    invert = prev.orientation !== current.orientation,
    prePieces = {},
    white = current.orientation === 'white';
  for (var pk in prev.pieces) {
    var piece = makePiece(pk, prev.pieces[pk], invert);
    prePieces[piece.key] = piece;
  }
  for (var i = 0; i < util.allKeys.length; i++) {
    var key = util.allKeys[i];
    if (key !== current.movable.dropped[1]) {
      var curP = current.pieces[key];
      var preP = prePieces[key];
      if (curP) {
        if (preP) {
          if (!samePiece(curP, preP)) {
            missings.push(preP);
            news.push(makePiece(key, curP, false));
          }
        } else
          news.push(makePiece(key, curP, false));
      } else if (preP)
        missings.push(preP);
    }
  }
  news.forEach(function(newP) {
    var preP = closer(newP, missings.filter(util.partial(samePiece, newP)));
    if (preP) {
      var orig = white ? preP.pos : newP.pos;
      var dest = white ? newP.pos : preP.pos;
      var vector = [(orig[0] - dest[0]) * width, (dest[1] - orig[1]) * height];
      anims[newP.key] = [vector, vector];
      animedOrigs.push(preP.key);
    }
  });
  missings.forEach(function(p) {
    if (
      p.key !== current.movable.dropped[0] &&
      !util.containsX(animedOrigs, p.key) &&
      !(current.items ? current.items.render(p.pos, p.key) : false)
    )
      fadings.push({
        piece: p,
        opacity: 1
      });
  });

  return {
    anims: anims,
    fadings: fadings
  };
}

function roundBy(n, by) {
  return Math.round(n * by) / by;
}

function go(data) {
  if (!data.animation.current.start) return; // animation was canceled
  var rest = 1 - (new Date().getTime() - data.animation.current.start) / data.animation.current.duration;
  if (rest <= 0) {
    data.animation.current = {};
    data.render();
  } else {
    var ease = easing.easeInOutCubic(rest);
    for (var key in data.animation.current.anims) {
      var cfg = data.animation.current.anims[key];
      cfg[1] = [roundBy(cfg[0][0] * ease, 10), roundBy(cfg[0][1] * ease, 10)];
    }
    for (var i in data.animation.current.fadings) {
      data.animation.current.fadings[i].opacity = roundBy(ease, 100);
    }
    data.render();
    util.requestAnimationFrame(function() {
      go(data);
    });
  }
}

function animate(transformation, data) {
  // clone data
  var prev = {
    orientation: data.orientation,
    pieces: {}
  };
  // clone pieces
  for (var key in data.pieces) {
    prev.pieces[key] = {
      role: data.pieces[key].role,
      color: data.pieces[key].color
    };
  }
  var result = transformation();
  if (data.animation.enabled) {
    var plan = computePlan(prev, data);
    if (Object.keys(plan.anims).length > 0 || plan.fadings.length > 0) {
      var alreadyRunning = data.animation.current.start;
      data.animation.current = {
        start: new Date().getTime(),
        duration: data.animation.duration,
        anims: plan.anims,
        fadings: plan.fadings
      };
      if (!alreadyRunning) go(data);
    } else {
      // don't animate, just render right away
      data.renderRAF();
    }
  } else {
    // animations are now disabled
    data.renderRAF();
  }
  return result;
}

// transformation is a function
// accepts board data and any number of arguments,
// and mutates the board.
module.exports = function(transformation, data, skip) {
  return function() {
    var transformationArgs = [data].concat(Array.prototype.slice.call(arguments, 0));
    if (!data.render) return transformation.apply(null, transformationArgs);
    else if (data.animation.enabled && !skip)
      return animate(util.partialApply(transformation, transformationArgs), data);
    else {
      var result = transformation.apply(null, transformationArgs);
      data.renderRAF();
      return result;
    }
  };
};

},{"./util":17}],5:[function(require,module,exports){
var board = require('./board');

module.exports = function(controller) {

  return {
    set: controller.set,
    toggleOrientation: controller.toggleOrientation,
    getOrientation: controller.getOrientation,
    getPieces: function() {
      return controller.data.pieces;
    },
    getMaterialDiff: function() {
      return board.getMaterialDiff(controller.data);
    },
    getFen: controller.getFen,
    move: controller.apiMove,
    newPiece: controller.apiNewPiece,
    setPieces: controller.setPieces,
    setCheck: controller.setCheck,
    playPremove: controller.playPremove,
    playPredrop: controller.playPredrop,
    cancelPremove: controller.cancelPremove,
    cancelPredrop: controller.cancelPredrop,
    cancelMove: controller.cancelMove,
    stop: controller.stop,
    explode: controller.explode,
    setAutoShapes: controller.setAutoShapes,
    setShapes: controller.setShapes,
    data: controller.data // directly exposes chessground state for more messing around
  };
};

},{"./board":6}],6:[function(require,module,exports){
var util = require('./util');
var premove = require('./premove');
var anim = require('./anim');
var hold = require('./hold');

function callUserFunction(f) {
  setTimeout(f, 1);
}

function toggleOrientation(data) {
  data.orientation = util.opposite(data.orientation);
}

function reset(data) {
  data.lastMove = null;
  setSelected(data, null);
  unsetPremove(data);
  unsetPredrop(data);
}

function setPieces(data, pieces) {
  Object.keys(pieces).forEach(function(key) {
    if (pieces[key]) data.pieces[key] = pieces[key];
    else delete data.pieces[key];
  });
  data.movable.dropped = [];
}

function setCheck(data, color) {
  var checkColor = color || data.turnColor;
  Object.keys(data.pieces).forEach(function(key) {
    if (data.pieces[key].color === checkColor && data.pieces[key].role === 'king') data.check = key;
  });
}

function setPremove(data, orig, dest) {
  unsetPredrop(data);
  data.premovable.current = [orig, dest];
  callUserFunction(util.partial(data.premovable.events.set, orig, dest));
}

function unsetPremove(data) {
  if (data.premovable.current) {
    data.premovable.current = null;
    callUserFunction(data.premovable.events.unset);
  }
}

function setPredrop(data, role, key) {
  unsetPremove(data);
  data.predroppable.current = {
    role: role,
    key: key
  };
  callUserFunction(util.partial(data.predroppable.events.set, role, key));
}

function unsetPredrop(data) {
  if (data.predroppable.current.key) {
    data.predroppable.current = {};
    callUserFunction(data.predroppable.events.unset);
  }
}

function tryAutoCastle(data, orig, dest) {
  if (!data.autoCastle) return;
  var king = data.pieces[dest];
  if (king.role !== 'king') return;
  var origPos = util.key2pos(orig);
  if (origPos[0] !== 5) return;
  if (origPos[1] !== 1 && origPos[1] !== 8) return;
  var destPos = util.key2pos(dest),
    oldRookPos, newRookPos, newKingPos;
  if (destPos[0] === 7 || destPos[0] === 8) {
    oldRookPos = util.pos2key([8, origPos[1]]);
    newRookPos = util.pos2key([6, origPos[1]]);
    newKingPos = util.pos2key([7, origPos[1]]);
  } else if (destPos[0] === 3 || destPos[0] === 1) {
    oldRookPos = util.pos2key([1, origPos[1]]);
    newRookPos = util.pos2key([4, origPos[1]]);
    newKingPos = util.pos2key([3, origPos[1]]);
  } else return;
  delete data.pieces[orig];
  delete data.pieces[dest];
  delete data.pieces[oldRookPos];
  data.pieces[newKingPos] = {
    role: 'king',
    color: king.color
  };
  data.pieces[newRookPos] = {
    role: 'rook',
    color: king.color
  };
}

function baseMove(data, orig, dest) {
  var success = anim(function() {
    if (orig === dest || !data.pieces[orig]) return false;
    var captured = (
      data.pieces[dest] &&
      data.pieces[dest].color !== data.pieces[orig].color
    ) ? data.pieces[dest] : null;
    callUserFunction(util.partial(data.events.move, orig, dest, captured));
    data.pieces[dest] = data.pieces[orig];
    delete data.pieces[orig];
    data.lastMove = [orig, dest];
    data.check = null;
    tryAutoCastle(data, orig, dest);
    callUserFunction(data.events.change);
    return true;
  }, data)();
  if (success) data.movable.dropped = [];
  return success;
}

function baseNewPiece(data, piece, key) {
  if (data.pieces[key]) return false;
  callUserFunction(util.partial(data.events.dropNewPiece, piece, key));
  data.pieces[key] = piece;
  data.lastMove = [key, key];
  data.check = null;
  callUserFunction(data.events.change);
  data.movable.dropped = [];
  data.movable.dests = {};
  data.turnColor = util.opposite(data.turnColor);
  data.renderRAF();
  return true;
}

function baseUserMove(data, orig, dest) {
  var result = baseMove(data, orig, dest);
  if (result) {
    data.movable.dests = {};
    data.turnColor = util.opposite(data.turnColor);
  }
  return result;
}

function apiMove(data, orig, dest) {
  return baseMove(data, orig, dest);
}

function apiNewPiece(data, piece, key) {
  return baseNewPiece(data, piece, key);
}

function userMove(data, orig, dest) {
  if (!dest) {
    hold.cancel();
    setSelected(data, null);
    if (data.movable.dropOff === 'trash') {
      delete data.pieces[orig];
      callUserFunction(data.events.change);
    }
  } else if (canMove(data, orig, dest)) {
    if (baseUserMove(data, orig, dest)) {
      var holdTime = hold.stop();
      setSelected(data, null);
      callUserFunction(util.partial(data.movable.events.after, orig, dest, {
        premove: false,
        holdTime: holdTime
      }));
      return true;
    }
  } else if (canPremove(data, orig, dest)) {
    setPremove(data, orig, dest);
    setSelected(data, null);
  } else if (isMovable(data, dest) || isPremovable(data, dest)) {
    setSelected(data, dest);
    hold.start();
  } else setSelected(data, null);
}

function dropNewPiece(data, orig, dest) {
  if (canDrop(data, orig, dest)) {
    var piece = data.pieces[orig];
    delete data.pieces[orig];
    baseNewPiece(data, piece, dest);
    data.movable.dropped = [];
    callUserFunction(util.partial(data.movable.events.afterNewPiece, piece.role, dest, {
      predrop: false
    }));
  } else if (canPredrop(data, orig, dest)) {
    setPredrop(data, data.pieces[orig].role, dest);
  } else {
    unsetPremove(data);
    unsetPredrop(data);
  }
  delete data.pieces[orig];
  setSelected(data, null);
}

function selectSquare(data, key) {
  if (data.selected) {
    if (key) {
      if (data.selectable.enabled && data.selected !== key) {
        if (userMove(data, data.selected, key)) data.stats.dragged = false;
      } else hold.start();
    } else {
      setSelected(data, null);
      hold.cancel();
    }
  } else if (isMovable(data, key) || isPremovable(data, key)) {
    setSelected(data, key);
    hold.start();
  }
  if (key) callUserFunction(util.partial(data.events.select, key));
}

function setSelected(data, key) {
  data.selected = key;
  if (key && isPremovable(data, key))
    data.premovable.dests = premove(data.pieces, key, data.premovable.castle);
  else
    data.premovable.dests = null;
}

function isMovable(data, orig) {
  var piece = data.pieces[orig];
  return piece && (
    data.movable.color === 'both' || (
      data.movable.color === piece.color &&
      data.turnColor === piece.color
    ));
}

function canMove(data, orig, dest) {
  return orig !== dest && isMovable(data, orig) && (
    data.movable.free || util.containsX(data.movable.dests[orig], dest)
  );
}

function canDrop(data, orig, dest) {
  var piece = data.pieces[orig];
  return piece && dest && (orig === dest || !data.pieces[dest]) && (
    data.movable.color === 'both' || (
      data.movable.color === piece.color &&
      data.turnColor === piece.color
    ));
}


function isPremovable(data, orig) {
  var piece = data.pieces[orig];
  return piece && data.premovable.enabled &&
    data.movable.color === piece.color &&
    data.turnColor !== piece.color;
}

function canPremove(data, orig, dest) {
  return orig !== dest &&
    isPremovable(data, orig) &&
    util.containsX(premove(data.pieces, orig, data.premovable.castle), dest);
}

function canPredrop(data, orig, dest) {
  var piece = data.pieces[orig];
  return piece && dest &&
    (!data.pieces[dest] || data.pieces[dest].color !== data.movable.color) &&
    data.predroppable.enabled &&
    (piece.role !== 'pawn' || (dest[1] !== '1' && dest[1] !== '8')) &&
    data.movable.color === piece.color &&
    data.turnColor !== piece.color;
}

function isDraggable(data, orig) {
  var piece = data.pieces[orig];
  return piece && data.draggable.enabled && (
    data.movable.color === 'both' || (
      data.movable.color === piece.color && (
        data.turnColor === piece.color || data.premovable.enabled
      )
    )
  );
}

function playPremove(data) {
  var move = data.premovable.current;
  if (!move) return;
  var orig = move[0],
    dest = move[1],
    success = false;
  if (canMove(data, orig, dest)) {
    if (baseUserMove(data, orig, dest)) {
      callUserFunction(util.partial(data.movable.events.after, orig, dest, {
        premove: true
      }));
      success = true;
    }
  }
  unsetPremove(data);
  return success;
}

function playPredrop(data, validate) {
  var drop = data.predroppable.current,
    success = false;
  if (!drop.key) return;
  if (validate(drop)) {
    var piece = {
      role: drop.role,
      color: data.movable.color
    };
    if (baseNewPiece(data, piece, drop.key)) {
      callUserFunction(util.partial(data.movable.events.afterNewPiece, drop.role, drop.key, {
        predrop: true
      }));
      success = true;
    }
  }
  unsetPredrop(data);
  return success;
}

function cancelMove(data) {
  unsetPremove(data);
  unsetPredrop(data);
  selectSquare(data, null);
}

function stop(data) {
  data.movable.color = null;
  data.movable.dests = {};
  cancelMove(data);
}

function getKeyAtDomPos(data, pos, bounds) {
  if (!bounds && !data.bounds) return;
  bounds = bounds || data.bounds(); // use provided value, or compute it
  var file = Math.ceil(8 * ((pos[0] - bounds.left) / bounds.width));
  file = data.orientation === 'white' ? file : 9 - file;
  var rank = Math.ceil(8 - (8 * ((pos[1] - bounds.top) / bounds.height)));
  rank = data.orientation === 'white' ? rank : 9 - rank;
  if (file > 0 && file < 9 && rank > 0 && rank < 9) return util.pos2key([file, rank]);
}

// {white: {pawn: 3 queen: 1}, black: {bishop: 2}}
function getMaterialDiff(data) {
  var counts = {
    king: 0,
    queen: 0,
    rook: 0,
    bishop: 0,
    knight: 0,
    pawn: 0
  };
  for (var k in data.pieces) {
    var p = data.pieces[k];
    counts[p.role] += ((p.color === 'white') ? 1 : -1);
  }
  var diff = {
    white: {},
    black: {}
  };
  for (var role in counts) {
    var c = counts[role];
    if (c > 0) diff.white[role] = c;
    else if (c < 0) diff.black[role] = -c;
  }
  return diff;
}

var pieceScores = {
  pawn: 1,
  knight: 3,
  bishop: 3,
  rook: 5,
  queen: 9,
  king: 0
};

function getScore(data) {
  var score = 0;
  for (var k in data.pieces) {
    score += pieceScores[data.pieces[k].role] * (data.pieces[k].color === 'white' ? 1 : -1);
  }
  return score;
}

module.exports = {
  reset: reset,
  toggleOrientation: toggleOrientation,
  setPieces: setPieces,
  setCheck: setCheck,
  selectSquare: selectSquare,
  setSelected: setSelected,
  isDraggable: isDraggable,
  canMove: canMove,
  userMove: userMove,
  dropNewPiece: dropNewPiece,
  apiMove: apiMove,
  apiNewPiece: apiNewPiece,
  playPremove: playPremove,
  playPredrop: playPredrop,
  unsetPremove: unsetPremove,
  unsetPredrop: unsetPredrop,
  cancelMove: cancelMove,
  stop: stop,
  getKeyAtDomPos: getKeyAtDomPos,
  getMaterialDiff: getMaterialDiff,
  getScore: getScore
};

},{"./anim":4,"./hold":14,"./premove":15,"./util":17}],7:[function(require,module,exports){
var merge = require('merge');
var board = require('./board');
var fen = require('./fen');

module.exports = function(data, config) {

  if (!config) return;

  // don't merge destinations. Just override.
  if (config.movable && config.movable.dests) delete data.movable.dests;

  merge.recursive(data, config);

  // if a fen was provided, replace the pieces
  if (data.fen) {
    data.pieces = fen.read(data.fen);
    data.check = config.check;
    data.drawable.shapes = [];
    delete data.fen;
  }

  if (data.check === true) board.setCheck(data);

  // forget about the last dropped piece
  data.movable.dropped = [];

  // fix move/premove dests
  if (data.selected) board.setSelected(data, data.selected);

  // no need for such short animations
  if (!data.animation.duration || data.animation.duration < 40)
    data.animation.enabled = false;
};

},{"./board":6,"./fen":13,"merge":2}],8:[function(require,module,exports){
var m = require('mithril');
var util = require('./util');

function renderCoords(elems, klass, orient) {
  var el = document.createElement('coords');
  el.className = klass;
  elems.forEach(function(content) {
    var f = document.createElement('coord');
    f.textContent = content;
    el.appendChild(f);
  });
  return el;
}

module.exports = function(orientation, el) {

  util.requestAnimationFrame(function() {
    var coords = document.createDocumentFragment();
    var orientClass = orientation === 'black' ? ' black' : '';
    coords.appendChild(renderCoords(util.ranks, 'ranks' + orientClass));
    coords.appendChild(renderCoords(util.files, 'files' + orientClass));
    el.appendChild(coords);
  });

  var orientation;

  return function(o) {
    if (o === orientation) return;
    orientation = o;
    $(el).find('coords').toggleClass('black', orientation === 'black');
  };
}

},{"./util":17,"mithril":3}],9:[function(require,module,exports){
var board = require('./board');
var data = require('./data');
var fen = require('./fen');
var configure = require('./configure');
var anim = require('./anim');
var drag = require('./drag');

module.exports = function(cfg) {

  this.data = data(cfg);

  this.vm = {
    exploding: false
  };

  this.getFen = function() {
    return fen.write(this.data.pieces);
  }.bind(this);

  this.getOrientation = function() {
    return this.data.orientation;
  }.bind(this);

  this.set = anim(configure, this.data);

  this.toggleOrientation = anim(board.toggleOrientation, this.data);

  this.setPieces = anim(board.setPieces, this.data);

  this.selectSquare = anim(board.selectSquare, this.data, true);

  this.apiMove = anim(board.apiMove, this.data);

  this.apiNewPiece = anim(board.apiNewPiece, this.data);

  this.playPremove = anim(board.playPremove, this.data);

  this.playPredrop = anim(board.playPredrop, this.data);

  this.cancelPremove = anim(board.unsetPremove, this.data, true);

  this.cancelPredrop = anim(board.unsetPredrop, this.data, true);

  this.setCheck = anim(board.setCheck, this.data, true);

  this.cancelMove = anim(function(data) {
    board.cancelMove(data);
    drag.cancel(data);
  }.bind(this), this.data, true);

  this.stop = anim(function(data) {
    board.stop(data);
    drag.cancel(data);
  }.bind(this), this.data, true);

  this.explode = function(keys) {
    if (!this.data.render) return;
    this.vm.exploding = {
      stage: 1,
      keys: keys
    };
    this.data.renderRAF();
    setTimeout(function() {
      this.vm.exploding.stage = 2;
      this.data.renderRAF();
      setTimeout(function() {
        this.vm.exploding = false;
        this.data.renderRAF();
      }.bind(this), 120);
    }.bind(this), 120);
  }.bind(this);

  this.setAutoShapes = function(shapes) {
    anim(function(data) {
      data.drawable.autoShapes = shapes;
    }, this.data, false)();
  }.bind(this);

  this.setShapes = function(shapes) {
    anim(function(data) {
      data.drawable.shapes = shapes;
    }, this.data, false)();
  }.bind(this);
};

},{"./anim":4,"./board":6,"./configure":7,"./data":10,"./drag":11,"./fen":13}],10:[function(require,module,exports){
var fen = require('./fen');
var configure = require('./configure');

module.exports = function(cfg) {
  var defaults = {
    pieces: fen.read(fen.initial),
    orientation: 'white', // board orientation. white | black
    turnColor: 'white', // turn to play. white | black
    check: null, // square currently in check "a2" | null
    lastMove: null, // squares part of the last move ["c3", "c4"] | null
    selected: null, // square currently selected "a1" | null
    coordinates: true, // include coords attributes
    render: null, // function that rerenders the board
    renderRAF: null, // function that rerenders the board using requestAnimationFrame
    element: null, // DOM element of the board, required for drag piece centering
    bounds: null, // function that calculates the board bounds
    autoCastle: false, // immediately complete the castle by moving the rook after king move
    viewOnly: false, // don't bind events: the user will never be able to move pieces around
    disableContextMenu: false, // because who needs a context menu on a chessboard
    resizable: true, // listens to chessground.resize on document.body to clear bounds cache
    pieceKey: false, // add a data-key attribute to piece elements
    highlight: {
      lastMove: true, // add last-move class to squares
      check: true, // add check class to squares
      dragOver: true // add drag-over class to square when dragging over it
    },
    animation: {
      enabled: true,
      duration: 200,
      /*{ // current
       *  start: timestamp,
       *  duration: ms,
       *  anims: {
       *    a2: [
       *      [-30, 50], // animation goal
       *      [-20, 37]  // animation current status
       *    ], ...
       *  },
       *  fading: [
       *    {
       *      pos: [80, 120], // position relative to the board
       *      opacity: 0.34,
       *      role: 'rook',
       *      color: 'black'
       *    }
       *  }
       *}*/
      current: {}
    },
    movable: {
      free: true, // all moves are valid - board editor
      color: 'both', // color that can move. white | black | both | null
      dests: {}, // valid moves. {"a2" ["a3" "a4"] "b1" ["a3" "c3"]} | null
      dropOff: 'revert', // when a piece is dropped outside the board. "revert" | "trash"
      dropped: [], // last dropped [orig, dest], not to be animated
      showDests: true, // whether to add the move-dest class on squares
      events: {
        after: function(orig, dest, metadata) {}, // called after the move has been played
        afterNewPiece: function(role, pos) {} // called after a new piece is dropped on the board
      }
    },
    premovable: {
      enabled: true, // allow premoves for color that can not move
      showDests: true, // whether to add the premove-dest class on squares
      castle: true, // whether to allow king castle premoves
      dests: [], // premove destinations for the current selection
      current: null, // keys of the current saved premove ["e2" "e4"] | null
      events: {
        set: function(orig, dest) {}, // called after the premove has been set
        unset: function() {} // called after the premove has been unset
      }
    },
    predroppable: {
      enabled: false, // allow predrops for color that can not move
      current: {}, // current saved predrop {role: 'knight', key: 'e4'} | {}
      events: {
        set: function(role, key) {}, // called after the predrop has been set
        unset: function() {} // called after the predrop has been unset
      }
    },
    draggable: {
      enabled: true, // allow moves & premoves to use drag'n drop
      distance: 3, // minimum distance to initiate a drag, in pixels
      autoDistance: true, // lets chessground set distance to zero when user drags pieces
      centerPiece: true, // center the piece on cursor at drag start
      showGhost: true, // show ghost of piece being dragged
      /*{ // current
       *  orig: "a2", // orig key of dragging piece
       *  rel: [100, 170] // x, y of the piece at original position
       *  pos: [20, -12] // relative current position
       *  dec: [4, -8] // piece center decay
       *  over: "b3" // square being moused over
       *  bounds: current cached board bounds
       *  started: whether the drag has started, as per the distance setting
       *}*/
      current: {}
    },
    selectable: {
      // disable to enforce dragging over click-click move
      enabled: true
    },
    stats: {
      // was last piece dragged or clicked?
      // needs default to false for touch
      dragged: !('ontouchstart' in window)
    },
    events: {
      change: function() {}, // called after the situation changes on the board
      // called after a piece has been moved.
      // capturedPiece is null or like {color: 'white', 'role': 'queen'}
      move: function(orig, dest, capturedPiece) {},
      dropNewPiece: function(role, pos) {},
      capture: function(key, piece) {}, // DEPRECATED called when a piece has been captured
      select: function(key) {} // called when a square is selected
    },
    items: null, // items on the board { render: key -> vdom }
    drawable: {
      enabled: false, // allows SVG drawings
      eraseOnClick: true,
      onChange: function(shapes) {},
      // user shapes
      shapes: [
        // {brush: 'green', orig: 'e8'},
        // {brush: 'yellow', orig: 'c4', dest: 'f7'}
      ],
      // computer shapes
      autoShapes: [
        // {brush: 'paleBlue', orig: 'e8'},
        // {brush: 'paleRed', orig: 'c4', dest: 'f7'}
      ],
      /*{ // current
       *  orig: "a2", // orig key of drawing
       *  pos: [20, -12] // relative current position
       *  dest: "b3" // square being moused over
       *  bounds: // current cached board bounds
       *  brush: 'green' // brush name for shape
       *}*/
      current: {},
      brushes: {
        green: {
          key: 'g',
          color: '#15781B',
          opacity: 1,
          lineWidth: 10
        },
        red: {
          key: 'r',
          color: '#882020',
          opacity: 1,
          lineWidth: 10
        },
        blue: {
          key: 'b',
          color: '#003088',
          opacity: 1,
          lineWidth: 10
        },
        yellow: {
          key: 'y',
          color: '#e68f00',
          opacity: 1,
          lineWidth: 10
        },
        paleBlue: {
          key: 'pb',
          color: '#003088',
          opacity: 0.3,
          lineWidth: 15
        },
        paleGreen: {
          key: 'pg',
          color: '#15781B',
          opacity: 0.35,
          lineWidth: 15
        }
      },
      // drawable SVG pieces, used for crazyhouse drop
      pieces: {
        baseUrl: 'https://lichess1.org/assets/piece/cburnett/'
      }
    }
  };

  configure(defaults, cfg || {});

  return defaults;
};

},{"./configure":7,"./fen":13}],11:[function(require,module,exports){
var board = require('./board');
var util = require('./util');
var draw = require('./draw');

var originTarget;

function hashPiece(piece) {
  return piece ? piece.color + piece.role : '';
}

function computeSquareBounds(data, bounds, key) {
  var pos = util.key2pos(key);
  if (data.orientation !== 'white') {
    pos[0] = 9 - pos[0];
    pos[1] = 9 - pos[1];
  }
  return {
    left: bounds.left + bounds.width * (pos[0] - 1) / 8,
    top: bounds.top + bounds.height * (8 - pos[1]) / 8,
    width: bounds.width / 8,
    height: bounds.height / 8
  };
}

function start(data, e) {
  if (e.button !== undefined && e.button !== 0) return; // only touch or left click
  if (e.touches && e.touches.length > 1) return; // support one finger touch only
  e.stopPropagation();
  e.preventDefault();
  originTarget = e.target;
  var previouslySelected = data.selected;
  var position = util.eventPosition(e);
  var bounds = data.bounds();
  var orig = board.getKeyAtDomPos(data, position, bounds);
  var piece = data.pieces[orig];
  if (!previouslySelected && (
    data.drawable.eraseOnClick ||
    (!piece || piece.color !== data.turnColor)
  )) draw.clear(data);
  if (data.viewOnly) return;
  var hadPremove = !!data.premovable.current;
  var hadPredrop = !!data.predroppable.current.key;
  board.selectSquare(data, orig);
  var stillSelected = data.selected === orig;
  if (piece && stillSelected && board.isDraggable(data, orig)) {
    var squareBounds = computeSquareBounds(data, bounds, orig);
    data.draggable.current = {
      previouslySelected: previouslySelected,
      orig: orig,
      piece: hashPiece(piece),
      rel: position,
      epos: position,
      pos: [0, 0],
      dec: data.draggable.centerPiece ? [
        position[0] - (squareBounds.left + squareBounds.width / 2),
        position[1] - (squareBounds.top + squareBounds.height / 2)
      ] : [0, 0],
      bounds: bounds,
      started: data.draggable.autoDistance && data.stats.dragged
    };
  } else {
    if (hadPremove) board.unsetPremove(data);
    if (hadPredrop) board.unsetPredrop(data);
  }
  processDrag(data);
}

function processDrag(data) {
  util.requestAnimationFrame(function() {
    var cur = data.draggable.current;
    if (cur.orig) {
      // cancel animations while dragging
      if (data.animation.current.start && data.animation.current.anims[cur.orig])
        data.animation.current = {};
      // if moving piece is gone, cancel
      if (hashPiece(data.pieces[cur.orig]) !== cur.piece) cancel(data);
      else {
        if (!cur.started && util.distance(cur.epos, cur.rel) >= data.draggable.distance)
          cur.started = true;
        if (cur.started) {
          cur.pos = [
            cur.epos[0] - cur.rel[0],
            cur.epos[1] - cur.rel[1]
          ];
          cur.over = board.getKeyAtDomPos(data, cur.epos, cur.bounds);
        }
      }
    }
    data.render();
    if (cur.orig) processDrag(data);
  });
}

function move(data, e) {
  if (e.touches && e.touches.length > 1) return; // support one finger touch only
  if (data.draggable.current.orig)
    data.draggable.current.epos = util.eventPosition(e);
}

function end(data, e) {
  var cur = data.draggable.current;
  var orig = cur ? cur.orig : null;
  if (!orig) return;
  // comparing with the origin target is an easy way to test that the end event
  // has the same touch origin
  if (e.type === "touchend" && originTarget !== e.target && !cur.newPiece) {
    data.draggable.current = {};
    return;
  }
  board.unsetPremove(data);
  board.unsetPredrop(data);
  var eventPos = util.eventPosition(e)
  var dest = eventPos ? board.getKeyAtDomPos(data, eventPos, cur.bounds) : cur.over;
  if (cur.started) {
    if (cur.newPiece) board.dropNewPiece(data, orig, dest);
    else {
      if (orig !== dest) data.movable.dropped = [orig, dest];
      if (board.userMove(data, orig, dest)) data.stats.dragged = true;
    }
  }
  if (orig === cur.previouslySelected && (orig === dest || !dest))
    board.setSelected(data, null);
  else if (!data.selectable.enabled) board.setSelected(data, null);
  data.draggable.current = {};
}

function cancel(data) {
  if (data.draggable.current.orig) {
    data.draggable.current = {};
    board.selectSquare(data, null);
  }
}

module.exports = {
  start: start,
  move: move,
  end: end,
  cancel: cancel,
  processDrag: processDrag // must be exposed for board editors
};

},{"./board":6,"./draw":12,"./util":17}],12:[function(require,module,exports){
var board = require('./board');
var util = require('./util');

var brushes = ['green', 'red', 'blue', 'yellow'];

function hashPiece(piece) {
  return piece ? piece.color + ' ' + piece.role : '';
}

function start(data, e) {
  if (e.touches && e.touches.length > 1) return; // support one finger touch only
  e.stopPropagation();
  e.preventDefault();
  board.cancelMove(data);
  var position = util.eventPosition(e);
  var bounds = data.bounds();
  var orig = board.getKeyAtDomPos(data, position, bounds);
  data.drawable.current = {
    orig: orig,
    epos: position,
    bounds: bounds,
    brush: brushes[(e.shiftKey & util.isRightButton(e)) + (e.altKey ? 2 : 0)]
  };
  processDraw(data);
}

function processDraw(data) {
  util.requestAnimationFrame(function() {
    var cur = data.drawable.current;
    if (cur.orig) {
      var dest = board.getKeyAtDomPos(data, cur.epos, cur.bounds);
      if (cur.orig === dest) cur.dest = undefined;
      else cur.dest = dest;
    }
    data.render();
    if (cur.orig) processDraw(data);
  });
}

function move(data, e) {
  if (data.drawable.current.orig)
    data.drawable.current.epos = util.eventPosition(e);
}

function end(data, e) {
  var drawable = data.drawable;
  var orig = drawable.current.orig;
  var dest = drawable.current.dest;
  if (orig && dest) addLine(drawable, orig, dest);
  else if (orig) addCircle(drawable, orig);
  drawable.current = {};
  data.render();
}

function cancel(data) {
  if (data.drawable.current.orig) data.drawable.current = {};
}

function clear(data) {
  if (data.drawable.shapes.length) {
    data.drawable.shapes = [];
    data.render();
    onChange(data.drawable);
  }
}

function not(f) {
  return function(x) {
    return !f(x);
  };
}

function addCircle(drawable, key) {
  var brush = drawable.current.brush;
  var sameCircle = function(s) {
    return s.orig === key && !s.dest;
  };
  var similar = drawable.shapes.filter(sameCircle)[0];
  if (similar) drawable.shapes = drawable.shapes.filter(not(sameCircle));
  if (!similar || similar.brush !== brush) drawable.shapes.push({
    brush: brush,
    orig: key
  });
  onChange(drawable);
}

function addLine(drawable, orig, dest) {
  var brush = drawable.current.brush;
  var sameLine = function(s) {
    return s.orig && s.dest && (
      (s.orig === orig && s.dest === dest) ||
      (s.dest === orig && s.orig === dest)
    );
  };
  var exists = drawable.shapes.filter(sameLine).length > 0;
  if (exists) drawable.shapes = drawable.shapes.filter(not(sameLine));
  else drawable.shapes.push({
    brush: brush,
    orig: orig,
    dest: dest
  });
  onChange(drawable);
}

function onChange(drawable) {
  drawable.onChange(drawable.shapes);
}

module.exports = {
  start: start,
  move: move,
  end: end,
  cancel: cancel,
  clear: clear,
  processDraw: processDraw
};

},{"./board":6,"./util":17}],13:[function(require,module,exports){
var util = require('./util');

var initial = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';

var roles = {
  p: "pawn",
  r: "rook",
  n: "knight",
  b: "bishop",
  q: "queen",
  k: "king"
};

var letters = {
  pawn: "p",
  rook: "r",
  knight: "n",
  bishop: "b",
  queen: "q",
  king: "k"
};

function read(fen) {
  if (fen === 'start') fen = initial;
  var pieces = {};
  fen.replace(/ .+$/, '').replace(/~/g, '').split('/').forEach(function(row, y) {
    var x = 0;
    row.split('').forEach(function(v) {
      var nb = parseInt(v);
      if (nb) x += nb;
      else {
        x++;
        pieces[util.pos2key([x, 8 - y])] = {
          role: roles[v.toLowerCase()],
          color: v === v.toLowerCase() ? 'black' : 'white'
        };
      }
    });
  });

  return pieces;
}

function write(pieces) {
  return [8, 7, 6, 5, 4, 3, 2].reduce(
    function(str, nb) {
      return str.replace(new RegExp(Array(nb + 1).join('1'), 'g'), nb);
    },
    util.invRanks.map(function(y) {
      return util.ranks.map(function(x) {
        var piece = pieces[util.pos2key([x, y])];
        if (piece) {
          var letter = letters[piece.role];
          return piece.color === 'white' ? letter.toUpperCase() : letter;
        } else return '1';
      }).join('');
    }).join('/'));
}

module.exports = {
  initial: initial,
  read: read,
  write: write
};

},{"./util":17}],14:[function(require,module,exports){
var startAt;

var start = function() {
  startAt = new Date();
};

var cancel = function() {
  startAt = null;
};

var stop = function() {
  if (!startAt) return 0;
  var time = new Date() - startAt;
  startAt = null;
  return time;
};

module.exports = {
  start: start,
  cancel: cancel,
  stop: stop
};

},{}],15:[function(require,module,exports){
var util = require('./util');

function diff(a, b) {
  return Math.abs(a - b);
}

function pawn(color, x1, y1, x2, y2) {
  return diff(x1, x2) < 2 && (
    color === 'white' ? (
      // allow 2 squares from 1 and 8, for horde
      y2 === y1 + 1 || (y1 <= 2 && y2 === (y1 + 2) && x1 === x2)
    ) : (
      y2 === y1 - 1 || (y1 >= 7 && y2 === (y1 - 2) && x1 === x2)
    )
  );
}

function knight(x1, y1, x2, y2) {
  var xd = diff(x1, x2);
  var yd = diff(y1, y2);
  return (xd === 1 && yd === 2) || (xd === 2 && yd === 1);
}

function bishop(x1, y1, x2, y2) {
  return diff(x1, x2) === diff(y1, y2);
}

function rook(x1, y1, x2, y2) {
  return x1 === x2 || y1 === y2;
}

function queen(x1, y1, x2, y2) {
  return bishop(x1, y1, x2, y2) || rook(x1, y1, x2, y2);
}

function king(color, rookFiles, canCastle, x1, y1, x2, y2) {
  return (
    diff(x1, x2) < 2 && diff(y1, y2) < 2
  ) || (
    canCastle && y1 === y2 && y1 === (color === 'white' ? 1 : 8) && (
      (x1 === 5 && (x2 === 3 || x2 === 7)) || util.containsX(rookFiles, x2)
    )
  );
}

function rookFilesOf(pieces, color) {
  return Object.keys(pieces).filter(function(key) {
    var piece = pieces[key];
    return piece && piece.color === color && piece.role === 'rook';
  }).map(function(key) {
    return util.key2pos(key)[0];
  });
}

function compute(pieces, key, canCastle) {
  var piece = pieces[key];
  var pos = util.key2pos(key);
  var mobility;
  switch (piece.role) {
    case 'pawn':
      mobility = pawn.bind(null, piece.color);
      break;
    case 'knight':
      mobility = knight;
      break;
    case 'bishop':
      mobility = bishop;
      break;
    case 'rook':
      mobility = rook;
      break;
    case 'queen':
      mobility = queen;
      break;
    case 'king':
      mobility = king.bind(null, piece.color, rookFilesOf(pieces, piece.color), canCastle);
      break;
  }
  return util.allPos.filter(function(pos2) {
    return (pos[0] !== pos2[0] || pos[1] !== pos2[1]) && mobility(pos[0], pos[1], pos2[0], pos2[1]);
  }).map(util.pos2key);
}

module.exports = compute;

},{"./util":17}],16:[function(require,module,exports){
var m = require('mithril');
var key2pos = require('./util').key2pos;
var isTrident = require('./util').isTrident;

function circleWidth(current, bounds) {
  return (current ? 2 : 4) / 512 * bounds.width;
}

function lineWidth(brush, current, bounds) {
  return (brush.lineWidth || 10) * (current ? 0.7 : 1) / 512 * bounds.width;
}

function opacity(brush, current) {
  return (brush.opacity || 1) * (current ? 0.6 : 1);
}

function arrowMargin(current, bounds) {
  return isTrident() ? 0 : ((current ? 10 : 20) / 512 * bounds.width);
}

function pos2px(pos, bounds) {
  var squareSize = bounds.width / 8;
  return [(pos[0] - 0.5) * squareSize, (8.5 - pos[1]) * squareSize];
}

function circle(brush, pos, current, bounds) {
  var o = pos2px(pos, bounds);
  var width = circleWidth(current, bounds);
  var radius = bounds.width / 16;
  return {
    tag: 'circle',
    attrs: {
      key: current ? 'current' : pos + brush.key,
      stroke: brush.color,
      'stroke-width': width,
      fill: 'none',
      opacity: opacity(brush, current),
      cx: o[0],
      cy: o[1],
      r: radius - width / 2
    }
  };
}

function arrow(brush, orig, dest, current, bounds) {
  var m = arrowMargin(current, bounds);
  var a = pos2px(orig, bounds);
  var b = pos2px(dest, bounds);
  var dx = b[0] - a[0],
    dy = b[1] - a[1],
    angle = Math.atan2(dy, dx);
  var xo = Math.cos(angle) * m,
    yo = Math.sin(angle) * m;
  return {
    tag: 'line',
    attrs: {
      key: current ? 'current' : orig + dest + brush.key,
      stroke: brush.color,
      'stroke-width': lineWidth(brush, current, bounds),
      'stroke-linecap': 'round',
      'marker-end': isTrident() ? null : 'url(#arrowhead-' + brush.key + ')',
      opacity: opacity(brush, current),
      x1: a[0],
      y1: a[1],
      x2: b[0] - xo,
      y2: b[1] - yo
    }
  };
}

function piece(cfg, pos, piece, bounds) {
  var o = pos2px(pos, bounds);
  var size = bounds.width / 8 * (piece.scale || 1);
  var name = piece.color === 'white' ? 'w' : 'b';
  name += (piece.role === 'knight' ? 'n' : piece.role[0]).toUpperCase();
  var href = cfg.baseUrl + name + '.svg';
  return {
    tag: 'image',
    attrs: {
      class: piece.color + ' ' + piece.role,
      x: o[0] - size / 2,
      y: o[1] - size / 2,
      width: size,
      height: size,
      href: href
    }
  };
}

function defs(brushes) {
  return {
    tag: 'defs',
    children: [
      brushes.map(function(brush) {
        return {
          key: brush.key,
          tag: 'marker',
          attrs: {
            id: 'arrowhead-' + brush.key,
            orient: 'auto',
            markerWidth: 4,
            markerHeight: 8,
            refX: 2.05,
            refY: 2.01
          },
          children: [{
            tag: 'path',
            attrs: {
              d: 'M0,0 V4 L3,2 Z',
              fill: brush.color
            }
          }]
        }
      })
    ]
  };
}

function orient(pos, color) {
  return color === 'white' ? pos : [9 - pos[0], 9 - pos[1]];
}

function renderShape(data, current, bounds) {
  return function(shape) {
    if (shape.orig && shape.dest) return arrow(
      data.drawable.brushes[shape.brush],
      orient(key2pos(shape.orig), data.orientation),
      orient(key2pos(shape.dest), data.orientation),
      current, bounds);
    else if (shape.piece) return piece(
      data.drawable.pieces,
      orient(key2pos(shape.orig), data.orientation),
      shape.piece,
      bounds);
    else if (shape.orig) return circle(
      data.drawable.brushes[shape.brush],
      orient(key2pos(shape.orig), data.orientation),
      current, bounds);
  };
}

module.exports = function(ctrl) {
  if (!ctrl.data.bounds) return;
  var d = ctrl.data.drawable;
  var allShapes = d.shapes.concat(d.autoShapes);
  if (!allShapes.length && !d.current.orig) return;
  var bounds = ctrl.data.bounds();
  if (bounds.width !== bounds.height) return;
  var usedBrushes = Object.keys(d.brushes).filter(function(name) {
    return (d.current && d.current.dest && d.current.brush === name) || allShapes.filter(function(s) {
      return s.dest && s.brush === name;
    }).length;
  }).map(function(name) {
    return d.brushes[name];
  });
  return {
    tag: 'svg',
    attrs: {
      key: 'svg'
    },
    children: [
      defs(usedBrushes),
      allShapes.map(renderShape(ctrl.data, false, bounds)),
      renderShape(ctrl.data, true, bounds)(d.current)
    ]
  };
}

},{"./util":17,"mithril":3}],17:[function(require,module,exports){
var files = "abcdefgh".split('');
var ranks = [1, 2, 3, 4, 5, 6, 7, 8];
var invRanks = [8, 7, 6, 5, 4, 3, 2, 1];
var fileNumbers = {
  a: 1,
  b: 2,
  c: 3,
  d: 4,
  e: 5,
  f: 6,
  g: 7,
  h: 8
};

function pos2key(pos) {
  return files[pos[0] - 1] + pos[1];
}

function key2pos(pos) {
  return [fileNumbers[pos[0]], parseInt(pos[1])];
}

function invertKey(key) {
  return files[8 - fileNumbers[key[0]]] + (9 - parseInt(key[1]));
}

var allPos = (function() {
  var ps = [];
  invRanks.forEach(function(y) {
    ranks.forEach(function(x) {
      ps.push([x, y]);
    });
  });
  return ps;
})();
var allKeys = allPos.map(pos2key);
var invKeys = allKeys.slice(0).reverse();

function classSet(classes) {
  var arr = [];
  for (var i in classes) {
    if (classes[i]) arr.push(i);
  }
  return arr.join(' ');
}

function opposite(color) {
  return color === 'white' ? 'black' : 'white';
}

function containsX(xs, x) {
  return xs && xs.indexOf(x) !== -1;
}

function distance(pos1, pos2) {
  return Math.sqrt(Math.pow(pos1[0] - pos2[0], 2) + Math.pow(pos1[1] - pos2[1], 2));
}

// this must be cached because of the access to document.body.style
var cachedTransformProp;

function computeTransformProp() {
  return 'transform' in document.body.style ?
    'transform' : 'webkitTransform' in document.body.style ?
    'webkitTransform' : 'mozTransform' in document.body.style ?
    'mozTransform' : 'oTransform' in document.body.style ?
    'oTransform' : 'msTransform';
}

function transformProp() {
  if (!cachedTransformProp) cachedTransformProp = computeTransformProp();
  return cachedTransformProp;
}

var cachedIsTrident = null;

function isTrident() {
  if (cachedIsTrident === null)
    cachedIsTrident = window.navigator.userAgent.indexOf('Trident/') > -1;
  return cachedIsTrident;
}

function translate(pos) {
  return 'translate(' + pos[0] + 'px,' + pos[1] + 'px)';
}

function eventPosition(e) {
  if (e.clientX || e.clientX === 0) return [e.clientX, e.clientY];
  if (e.touches && e.targetTouches[0]) return [e.targetTouches[0].clientX, e.targetTouches[0].clientY];
}

function partialApply(fn, args) {
  return fn.bind.apply(fn, [null].concat(args));
}

function partial() {
  return partialApply(arguments[0], Array.prototype.slice.call(arguments, 1));
}

function isRightButton(e) {
  return e.buttons === 2 || e.button === 2;
}

function memo(f) {
  var v, ret = function() {
    if (v === undefined) v = f();
    return v;
  };
  ret.clear = function() {
    v = undefined;
  }
  return ret;
}

module.exports = {
  files: files,
  ranks: ranks,
  invRanks: invRanks,
  allPos: allPos,
  allKeys: allKeys,
  invKeys: invKeys,
  pos2key: pos2key,
  key2pos: key2pos,
  invertKey: invertKey,
  classSet: classSet,
  opposite: opposite,
  translate: translate,
  containsX: containsX,
  distance: distance,
  eventPosition: eventPosition,
  partialApply: partialApply,
  partial: partial,
  transformProp: transformProp,
  isTrident: isTrident,
  requestAnimationFrame: (window.requestAnimationFrame || window.setTimeout).bind(window),
  isRightButton: isRightButton,
  memo: memo
};

},{}],18:[function(require,module,exports){
var drag = require('./drag');
var draw = require('./draw');
var util = require('./util');
var svg = require('./svg');
var makeCoords = require('./coords');
var m = require('mithril');

var pieceTag = 'piece';
var squareTag = 'square';

function pieceClass(p) {
  return p.role + ' ' + p.color;
}

function renderPiece(d, key, ctx) {
  var attrs = {
    key: 'p' + key,
    style: {},
    class: pieceClass(d.pieces[key])
  };
  var translate = posToTranslate(util.key2pos(key), ctx);
  var draggable = d.draggable.current;
  if (draggable.orig === key && draggable.started) {
    translate[0] += draggable.pos[0] + draggable.dec[0];
    translate[1] += draggable.pos[1] + draggable.dec[1];
    attrs.class += ' dragging';
  } else if (d.animation.current.anims) {
    var animation = d.animation.current.anims[key];
    if (animation) {
      translate[0] += animation[1][0];
      translate[1] += animation[1][1];
    }
  }
  attrs.style[ctx.transformProp] = util.translate(translate);
  if (d.pieceKey) attrs['data-key'] = key;
  return {
    tag: pieceTag,
    attrs: attrs
  };
}

function renderSquare(key, classes, ctx) {
  var attrs = {
    key: 's' + key,
    class: classes,
    style: {}
  };
  attrs.style[ctx.transformProp] = util.translate(posToTranslate(util.key2pos(key), ctx));
  return {
    tag: squareTag,
    attrs: attrs
  };
}

function posToTranslate(pos, ctx) {
  return [
    (ctx.asWhite ? pos[0] - 1 : 8 - pos[0]) * ctx.bounds.width / 8, (ctx.asWhite ? 8 - pos[1] : pos[1] - 1) * ctx.bounds.height / 8
  ];
}

function renderGhost(key, piece, ctx) {
  if (!piece) return;
  var attrs = {
    key: 'g' + key,
    style: {},
    class: pieceClass(piece) + ' ghost'
  };
  attrs.style[ctx.transformProp] = util.translate(posToTranslate(util.key2pos(key), ctx));
  return {
    tag: pieceTag,
    attrs: attrs
  };
}

function renderFading(cfg, ctx) {
  var attrs = {
    key: 'f' + cfg.piece.key,
    class: 'fading ' + pieceClass(cfg.piece),
    style: {
      opacity: cfg.opacity
    }
  };
  attrs.style[ctx.transformProp] = util.translate(posToTranslate(cfg.piece.pos, ctx));
  return {
    tag: pieceTag,
    attrs: attrs
  };
}

function addSquare(squares, key, klass) {
  if (squares[key]) squares[key].push(klass);
  else squares[key] = [klass];
}

function renderSquares(ctrl, ctx) {
  var d = ctrl.data;
  var squares = {};
  if (d.lastMove && d.highlight.lastMove) d.lastMove.forEach(function(k) {
    addSquare(squares, k, 'last-move');
  });
  if (d.check && d.highlight.check) addSquare(squares, d.check, 'check');
  if (d.selected) {
    addSquare(squares, d.selected, 'selected');
    var over = d.draggable.current.over;
    var dests = d.movable.dests[d.selected];
    if (dests) dests.forEach(function(k) {
      if (k === over) addSquare(squares, k, 'move-dest drag-over');
      else if (d.movable.showDests) addSquare(squares, k, 'move-dest' + (d.pieces[k] ? ' oc' : ''));
    });
    var pDests = d.premovable.dests;
    if (pDests) pDests.forEach(function(k) {
      if (k === over) addSquare(squares, k, 'premove-dest drag-over');
      else if (d.movable.showDests) addSquare(squares, k, 'premove-dest' + (d.pieces[k] ? ' oc' : ''));
    });
  }
  var premove = d.premovable.current;
  if (premove) premove.forEach(function(k) {
    addSquare(squares, k, 'current-premove');
  });
  else if (d.predroppable.current.key)
    addSquare(squares, d.predroppable.current.key, 'current-premove');

  if (ctrl.vm.exploding) ctrl.vm.exploding.keys.forEach(function(k) {
    addSquare(squares, k, 'exploding' + ctrl.vm.exploding.stage);
  });

  var dom = [];
  if (d.items) {
    for (var i = 0; i < 64; i++) {
      var key = util.allKeys[i];
      var square = squares[key];
      var item = d.items.render(util.key2pos(key), key);
      if (square || item) {
        var sq = renderSquare(key, square ? square.join(' ') + (item ? ' has-item' : '') : 'has-item', ctx);
        if (item) sq.children = [item];
        dom.push(sq);
      }
    }
  } else {
    for (var key in squares)
      dom.push(renderSquare(key, squares[key].join(' '), ctx));
  }
  return dom;
}

function renderContent(ctrl) {
  var d = ctrl.data;
  if (!d.bounds) return;
  var ctx = {
    asWhite: d.orientation === 'white',
    bounds: d.bounds(),
    transformProp: util.transformProp()
  };
  var children = renderSquares(ctrl, ctx);
  if (d.animation.current.fadings)
    d.animation.current.fadings.forEach(function(p) {
      children.push(renderFading(p, ctx));
    });

  // must insert pieces in the right order
  // for 3D to display correctly
  var keys = ctx.asWhite ? util.allKeys : util.invKeys;
  if (d.items)
    for (var i = 0; i < 64; i++) {
      if (d.pieces[keys[i]] && !d.items.render(util.key2pos(keys[i]), keys[i]))
        children.push(renderPiece(d, keys[i], ctx));
    } else
      for (var i = 0; i < 64; i++) {
        if (d.pieces[keys[i]]) children.push(renderPiece(d, keys[i], ctx));
      }

  if (d.draggable.showGhost) {
    var dragOrig = d.draggable.current.orig;
    if (dragOrig && !d.draggable.current.newPiece)
      children.push(renderGhost(dragOrig, d.pieces[dragOrig], ctx));
  }
  if (d.drawable.enabled) children.push(svg(ctrl));
  return children;
}

function startDragOrDraw(d) {
  return function(e) {
    if (util.isRightButton(e) && d.draggable.current.orig) {
      if (d.draggable.current.newPiece) delete d.pieces[d.draggable.current.orig];
      d.draggable.current = {}
      d.selected = null;
    } else if ((e.shiftKey || util.isRightButton(e)) && d.drawable.enabled) draw.start(d, e);
    else drag.start(d, e);
  };
}

function dragOrDraw(d, withDrag, withDraw) {
  return function(e) {
    if ((e.shiftKey || util.isRightButton(e)) && d.drawable.enabled) withDraw(d, e);
    else if (!d.viewOnly) withDrag(d, e);
  };
}

function bindEvents(ctrl, el, context) {
  var d = ctrl.data;
  var onstart = startDragOrDraw(d);
  var onmove = dragOrDraw(d, drag.move, draw.move);
  var onend = dragOrDraw(d, drag.end, draw.end);
  var startEvents = ['touchstart', 'mousedown'];
  var moveEvents = ['touchmove', 'mousemove'];
  var endEvents = ['touchend', 'mouseup'];
  startEvents.forEach(function(ev) {
    el.addEventListener(ev, onstart);
  });
  moveEvents.forEach(function(ev) {
    document.addEventListener(ev, onmove);
  });
  endEvents.forEach(function(ev) {
    document.addEventListener(ev, onend);
  });
  context.onunload = function() {
    startEvents.forEach(function(ev) {
      el.removeEventListener(ev, onstart);
    });
    moveEvents.forEach(function(ev) {
      document.removeEventListener(ev, onmove);
    });
    endEvents.forEach(function(ev) {
      document.removeEventListener(ev, onend);
    });
  };
}

function renderBoard(ctrl) {
  var d = ctrl.data;
  return {
    tag: 'div',
    attrs: {
      class: 'cg-board orientation-' + d.orientation,
      config: function(el, isUpdate, context) {
        if (isUpdate) return;
        if (!d.viewOnly || d.drawable.enabled)
          bindEvents(ctrl, el, context);
        // this function only repaints the board itself.
        // it's called when dragging or animating pieces,
        // to prevent the full application embedding chessground
        // rendering on every animation frame
        d.render = function() {
          m.render(el, renderContent(ctrl));
        };
        d.renderRAF = function() {
          util.requestAnimationFrame(d.render);
        };
        d.bounds = util.memo(el.getBoundingClientRect.bind(el));
        d.element = el;
        d.render();
      }
    },
    children: []
  };
}

module.exports = function(ctrl) {
  var d = ctrl.data;
  return {
    tag: 'div',
    attrs: {
      config: function(el, isUpdate, ctx) {
        if (isUpdate) {
          if (ctx.coords) ctx.coords(d.orientation);
          return;
        }
        if (d.coordinates) ctx.coords = makeCoords(ctrl.getOrientation(), el);
        el.addEventListener('contextmenu', function(e) {
          if (d.disableContextMenu || d.drawable.enabled) {
            e.preventDefault();
            return false;
          }
        });
        if (d.resizable)
          document.body.addEventListener('chessground.resize', function(e) {
            d.bounds.clear();
            d.render();
          }, false);
        ['onscroll', 'onresize'].forEach(function(n) {
          var prev = window[n];
          window[n] = function() {
            prev && prev();
            d.bounds.clear();
          };
        });
      },
      class: [
        'cg-board-wrap',
        d.viewOnly ? 'view-only' : 'manipulable'
      ].join(' ')
    },
    children: [renderBoard(ctrl)]
  };
};

},{"./coords":8,"./drag":11,"./draw":12,"./svg":16,"./util":17,"mithril":3}]},{},[1])(1)
});
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJzb3VyY2VzIjpbIm5vZGVfbW9kdWxlcy9icm93c2VyLXBhY2svX3ByZWx1ZGUuanMiLCJzcmMvbWFpbi5qcyIsIm5vZGVfbW9kdWxlcy9tZXJnZS9tZXJnZS5qcyIsIm5vZGVfbW9kdWxlcy9taXRocmlsL21pdGhyaWwuanMiLCJzcmMvYW5pbS5qcyIsInNyYy9hcGkuanMiLCJzcmMvYm9hcmQuanMiLCJzcmMvY29uZmlndXJlLmpzIiwic3JjL2Nvb3Jkcy5qcyIsInNyYy9jdHJsLmpzIiwic3JjL2RhdGEuanMiLCJzcmMvZHJhZy5qcyIsInNyYy9kcmF3LmpzIiwic3JjL2Zlbi5qcyIsInNyYy9ob2xkLmpzIiwic3JjL3ByZW1vdmUuanMiLCJzcmMvc3ZnLmpzIiwic3JjL3V0aWwuanMiLCJzcmMvdmlldy5qcyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiQUFBQTtBQ0FBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQ3hCQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTs7QUM5S0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQzkzQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDeEtBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDL0JBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQ2xaQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTs7QUNqQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQ2hDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTs7QUNwRkE7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTs7QUMzTEE7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQzVJQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDcEhBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDaEVBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDdEJBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQ3BGQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7O0FDdktBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBOztBQzFJQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBIiwiZmlsZSI6ImdlbmVyYXRlZC5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzQ29udGVudCI6WyIoZnVuY3Rpb24gZSh0LG4scil7ZnVuY3Rpb24gcyhvLHUpe2lmKCFuW29dKXtpZighdFtvXSl7dmFyIGE9dHlwZW9mIHJlcXVpcmU9PVwiZnVuY3Rpb25cIiYmcmVxdWlyZTtpZighdSYmYSlyZXR1cm4gYShvLCEwKTtpZihpKXJldHVybiBpKG8sITApO3ZhciBmPW5ldyBFcnJvcihcIkNhbm5vdCBmaW5kIG1vZHVsZSAnXCIrbytcIidcIik7dGhyb3cgZi5jb2RlPVwiTU9EVUxFX05PVF9GT1VORFwiLGZ9dmFyIGw9bltvXT17ZXhwb3J0czp7fX07dFtvXVswXS5jYWxsKGwuZXhwb3J0cyxmdW5jdGlvbihlKXt2YXIgbj10W29dWzFdW2VdO3JldHVybiBzKG4/bjplKX0sbCxsLmV4cG9ydHMsZSx0LG4scil9cmV0dXJuIG5bb10uZXhwb3J0c312YXIgaT10eXBlb2YgcmVxdWlyZT09XCJmdW5jdGlvblwiJiZyZXF1aXJlO2Zvcih2YXIgbz0wO288ci5sZW5ndGg7bysrKXMocltvXSk7cmV0dXJuIHN9KSIsInZhciBtID0gcmVxdWlyZSgnbWl0aHJpbCcpO1xyXG52YXIgY3RybCA9IHJlcXVpcmUoJy4vY3RybCcpO1xyXG52YXIgdmlldyA9IHJlcXVpcmUoJy4vdmlldycpO1xyXG52YXIgYXBpID0gcmVxdWlyZSgnLi9hcGknKTtcclxuXHJcbi8vIGZvciB1c2FnZSBvdXRzaWRlIG9mIG1pdGhyaWxcclxuZnVuY3Rpb24gaW5pdChlbGVtZW50LCBjb25maWcpIHtcclxuXHJcbiAgdmFyIGNvbnRyb2xsZXIgPSBuZXcgY3RybChjb25maWcpO1xyXG5cclxuICBtLnJlbmRlcihlbGVtZW50LCB2aWV3KGNvbnRyb2xsZXIpKTtcclxuXHJcbiAgcmV0dXJuIGFwaShjb250cm9sbGVyKTtcclxufVxyXG5cclxubW9kdWxlLmV4cG9ydHMgPSBpbml0O1xyXG5tb2R1bGUuZXhwb3J0cy5jb250cm9sbGVyID0gY3RybDtcclxubW9kdWxlLmV4cG9ydHMudmlldyA9IHZpZXc7XHJcbm1vZHVsZS5leHBvcnRzLmZlbiA9IHJlcXVpcmUoJy4vZmVuJyk7XHJcbm1vZHVsZS5leHBvcnRzLnV0aWwgPSByZXF1aXJlKCcuL3V0aWwnKTtcclxubW9kdWxlLmV4cG9ydHMuY29uZmlndXJlID0gcmVxdWlyZSgnLi9jb25maWd1cmUnKTtcclxubW9kdWxlLmV4cG9ydHMuYW5pbSA9IHJlcXVpcmUoJy4vYW5pbScpO1xyXG5tb2R1bGUuZXhwb3J0cy5ib2FyZCA9IHJlcXVpcmUoJy4vYm9hcmQnKTtcclxubW9kdWxlLmV4cG9ydHMuZHJhZyA9IHJlcXVpcmUoJy4vZHJhZycpO1xyXG4iLCIvKiFcclxuICogQG5hbWUgSmF2YVNjcmlwdC9Ob2RlSlMgTWVyZ2UgdjEuMi4wXHJcbiAqIEBhdXRob3IgeWVpa29zXHJcbiAqIEByZXBvc2l0b3J5IGh0dHBzOi8vZ2l0aHViLmNvbS95ZWlrb3MvanMubWVyZ2VcclxuXHJcbiAqIENvcHlyaWdodCAyMDE0IHllaWtvcyAtIE1JVCBsaWNlbnNlXHJcbiAqIGh0dHBzOi8vcmF3LmdpdGh1Yi5jb20veWVpa29zL2pzLm1lcmdlL21hc3Rlci9MSUNFTlNFXHJcbiAqL1xyXG5cclxuOyhmdW5jdGlvbihpc05vZGUpIHtcclxuXHJcblx0LyoqXHJcblx0ICogTWVyZ2Ugb25lIG9yIG1vcmUgb2JqZWN0cyBcclxuXHQgKiBAcGFyYW0gYm9vbD8gY2xvbmVcclxuXHQgKiBAcGFyYW0gbWl4ZWQsLi4uIGFyZ3VtZW50c1xyXG5cdCAqIEByZXR1cm4gb2JqZWN0XHJcblx0ICovXHJcblxyXG5cdHZhciBQdWJsaWMgPSBmdW5jdGlvbihjbG9uZSkge1xyXG5cclxuXHRcdHJldHVybiBtZXJnZShjbG9uZSA9PT0gdHJ1ZSwgZmFsc2UsIGFyZ3VtZW50cyk7XHJcblxyXG5cdH0sIHB1YmxpY05hbWUgPSAnbWVyZ2UnO1xyXG5cclxuXHQvKipcclxuXHQgKiBNZXJnZSB0d28gb3IgbW9yZSBvYmplY3RzIHJlY3Vyc2l2ZWx5IFxyXG5cdCAqIEBwYXJhbSBib29sPyBjbG9uZVxyXG5cdCAqIEBwYXJhbSBtaXhlZCwuLi4gYXJndW1lbnRzXHJcblx0ICogQHJldHVybiBvYmplY3RcclxuXHQgKi9cclxuXHJcblx0UHVibGljLnJlY3Vyc2l2ZSA9IGZ1bmN0aW9uKGNsb25lKSB7XHJcblxyXG5cdFx0cmV0dXJuIG1lcmdlKGNsb25lID09PSB0cnVlLCB0cnVlLCBhcmd1bWVudHMpO1xyXG5cclxuXHR9O1xyXG5cclxuXHQvKipcclxuXHQgKiBDbG9uZSB0aGUgaW5wdXQgcmVtb3ZpbmcgYW55IHJlZmVyZW5jZVxyXG5cdCAqIEBwYXJhbSBtaXhlZCBpbnB1dFxyXG5cdCAqIEByZXR1cm4gbWl4ZWRcclxuXHQgKi9cclxuXHJcblx0UHVibGljLmNsb25lID0gZnVuY3Rpb24oaW5wdXQpIHtcclxuXHJcblx0XHR2YXIgb3V0cHV0ID0gaW5wdXQsXHJcblx0XHRcdHR5cGUgPSB0eXBlT2YoaW5wdXQpLFxyXG5cdFx0XHRpbmRleCwgc2l6ZTtcclxuXHJcblx0XHRpZiAodHlwZSA9PT0gJ2FycmF5Jykge1xyXG5cclxuXHRcdFx0b3V0cHV0ID0gW107XHJcblx0XHRcdHNpemUgPSBpbnB1dC5sZW5ndGg7XHJcblxyXG5cdFx0XHRmb3IgKGluZGV4PTA7aW5kZXg8c2l6ZTsrK2luZGV4KVxyXG5cclxuXHRcdFx0XHRvdXRwdXRbaW5kZXhdID0gUHVibGljLmNsb25lKGlucHV0W2luZGV4XSk7XHJcblxyXG5cdFx0fSBlbHNlIGlmICh0eXBlID09PSAnb2JqZWN0Jykge1xyXG5cclxuXHRcdFx0b3V0cHV0ID0ge307XHJcblxyXG5cdFx0XHRmb3IgKGluZGV4IGluIGlucHV0KVxyXG5cclxuXHRcdFx0XHRvdXRwdXRbaW5kZXhdID0gUHVibGljLmNsb25lKGlucHV0W2luZGV4XSk7XHJcblxyXG5cdFx0fVxyXG5cclxuXHRcdHJldHVybiBvdXRwdXQ7XHJcblxyXG5cdH07XHJcblxyXG5cdC8qKlxyXG5cdCAqIE1lcmdlIHR3byBvYmplY3RzIHJlY3Vyc2l2ZWx5XHJcblx0ICogQHBhcmFtIG1peGVkIGlucHV0XHJcblx0ICogQHBhcmFtIG1peGVkIGV4dGVuZFxyXG5cdCAqIEByZXR1cm4gbWl4ZWRcclxuXHQgKi9cclxuXHJcblx0ZnVuY3Rpb24gbWVyZ2VfcmVjdXJzaXZlKGJhc2UsIGV4dGVuZCkge1xyXG5cclxuXHRcdGlmICh0eXBlT2YoYmFzZSkgIT09ICdvYmplY3QnKVxyXG5cclxuXHRcdFx0cmV0dXJuIGV4dGVuZDtcclxuXHJcblx0XHRmb3IgKHZhciBrZXkgaW4gZXh0ZW5kKSB7XHJcblxyXG5cdFx0XHRpZiAodHlwZU9mKGJhc2Vba2V5XSkgPT09ICdvYmplY3QnICYmIHR5cGVPZihleHRlbmRba2V5XSkgPT09ICdvYmplY3QnKSB7XHJcblxyXG5cdFx0XHRcdGJhc2Vba2V5XSA9IG1lcmdlX3JlY3Vyc2l2ZShiYXNlW2tleV0sIGV4dGVuZFtrZXldKTtcclxuXHJcblx0XHRcdH0gZWxzZSB7XHJcblxyXG5cdFx0XHRcdGJhc2Vba2V5XSA9IGV4dGVuZFtrZXldO1xyXG5cclxuXHRcdFx0fVxyXG5cclxuXHRcdH1cclxuXHJcblx0XHRyZXR1cm4gYmFzZTtcclxuXHJcblx0fVxyXG5cclxuXHQvKipcclxuXHQgKiBNZXJnZSB0d28gb3IgbW9yZSBvYmplY3RzXHJcblx0ICogQHBhcmFtIGJvb2wgY2xvbmVcclxuXHQgKiBAcGFyYW0gYm9vbCByZWN1cnNpdmVcclxuXHQgKiBAcGFyYW0gYXJyYXkgYXJndlxyXG5cdCAqIEByZXR1cm4gb2JqZWN0XHJcblx0ICovXHJcblxyXG5cdGZ1bmN0aW9uIG1lcmdlKGNsb25lLCByZWN1cnNpdmUsIGFyZ3YpIHtcclxuXHJcblx0XHR2YXIgcmVzdWx0ID0gYXJndlswXSxcclxuXHRcdFx0c2l6ZSA9IGFyZ3YubGVuZ3RoO1xyXG5cclxuXHRcdGlmIChjbG9uZSB8fCB0eXBlT2YocmVzdWx0KSAhPT0gJ29iamVjdCcpXHJcblxyXG5cdFx0XHRyZXN1bHQgPSB7fTtcclxuXHJcblx0XHRmb3IgKHZhciBpbmRleD0wO2luZGV4PHNpemU7KytpbmRleCkge1xyXG5cclxuXHRcdFx0dmFyIGl0ZW0gPSBhcmd2W2luZGV4XSxcclxuXHJcblx0XHRcdFx0dHlwZSA9IHR5cGVPZihpdGVtKTtcclxuXHJcblx0XHRcdGlmICh0eXBlICE9PSAnb2JqZWN0JykgY29udGludWU7XHJcblxyXG5cdFx0XHRmb3IgKHZhciBrZXkgaW4gaXRlbSkge1xyXG5cclxuXHRcdFx0XHR2YXIgc2l0ZW0gPSBjbG9uZSA/IFB1YmxpYy5jbG9uZShpdGVtW2tleV0pIDogaXRlbVtrZXldO1xyXG5cclxuXHRcdFx0XHRpZiAocmVjdXJzaXZlKSB7XHJcblxyXG5cdFx0XHRcdFx0cmVzdWx0W2tleV0gPSBtZXJnZV9yZWN1cnNpdmUocmVzdWx0W2tleV0sIHNpdGVtKTtcclxuXHJcblx0XHRcdFx0fSBlbHNlIHtcclxuXHJcblx0XHRcdFx0XHRyZXN1bHRba2V5XSA9IHNpdGVtO1xyXG5cclxuXHRcdFx0XHR9XHJcblxyXG5cdFx0XHR9XHJcblxyXG5cdFx0fVxyXG5cclxuXHRcdHJldHVybiByZXN1bHQ7XHJcblxyXG5cdH1cclxuXHJcblx0LyoqXHJcblx0ICogR2V0IHR5cGUgb2YgdmFyaWFibGVcclxuXHQgKiBAcGFyYW0gbWl4ZWQgaW5wdXRcclxuXHQgKiBAcmV0dXJuIHN0cmluZ1xyXG5cdCAqXHJcblx0ICogQHNlZSBodHRwOi8vanNwZXJmLmNvbS90eXBlb2Z2YXJcclxuXHQgKi9cclxuXHJcblx0ZnVuY3Rpb24gdHlwZU9mKGlucHV0KSB7XHJcblxyXG5cdFx0cmV0dXJuICh7fSkudG9TdHJpbmcuY2FsbChpbnB1dCkuc2xpY2UoOCwgLTEpLnRvTG93ZXJDYXNlKCk7XHJcblxyXG5cdH1cclxuXHJcblx0aWYgKGlzTm9kZSkge1xyXG5cclxuXHRcdG1vZHVsZS5leHBvcnRzID0gUHVibGljO1xyXG5cclxuXHR9IGVsc2Uge1xyXG5cclxuXHRcdHdpbmRvd1twdWJsaWNOYW1lXSA9IFB1YmxpYztcclxuXHJcblx0fVxyXG5cclxufSkodHlwZW9mIG1vZHVsZSA9PT0gJ29iamVjdCcgJiYgbW9kdWxlICYmIHR5cGVvZiBtb2R1bGUuZXhwb3J0cyA9PT0gJ29iamVjdCcgJiYgbW9kdWxlLmV4cG9ydHMpOyIsInZhciBtID0gKGZ1bmN0aW9uIGFwcCh3aW5kb3csIHVuZGVmaW5lZCkge1xyXG5cdFwidXNlIHN0cmljdFwiO1xyXG4gIFx0dmFyIFZFUlNJT04gPSBcInYwLjIuMVwiO1xyXG5cdGZ1bmN0aW9uIGlzRnVuY3Rpb24ob2JqZWN0KSB7XHJcblx0XHRyZXR1cm4gdHlwZW9mIG9iamVjdCA9PT0gXCJmdW5jdGlvblwiO1xyXG5cdH1cclxuXHRmdW5jdGlvbiBpc09iamVjdChvYmplY3QpIHtcclxuXHRcdHJldHVybiB0eXBlLmNhbGwob2JqZWN0KSA9PT0gXCJbb2JqZWN0IE9iamVjdF1cIjtcclxuXHR9XHJcblx0ZnVuY3Rpb24gaXNTdHJpbmcob2JqZWN0KSB7XHJcblx0XHRyZXR1cm4gdHlwZS5jYWxsKG9iamVjdCkgPT09IFwiW29iamVjdCBTdHJpbmddXCI7XHJcblx0fVxyXG5cdHZhciBpc0FycmF5ID0gQXJyYXkuaXNBcnJheSB8fCBmdW5jdGlvbiAob2JqZWN0KSB7XHJcblx0XHRyZXR1cm4gdHlwZS5jYWxsKG9iamVjdCkgPT09IFwiW29iamVjdCBBcnJheV1cIjtcclxuXHR9O1xyXG5cdHZhciB0eXBlID0ge30udG9TdHJpbmc7XHJcblx0dmFyIHBhcnNlciA9IC8oPzooXnwjfFxcLikoW14jXFwuXFxbXFxdXSspKXwoXFxbLis/XFxdKS9nLCBhdHRyUGFyc2VyID0gL1xcWyguKz8pKD86PShcInwnfCkoLio/KVxcMik/XFxdLztcclxuXHR2YXIgdm9pZEVsZW1lbnRzID0gL14oQVJFQXxCQVNFfEJSfENPTHxDT01NQU5EfEVNQkVEfEhSfElNR3xJTlBVVHxLRVlHRU58TElOS3xNRVRBfFBBUkFNfFNPVVJDRXxUUkFDS3xXQlIpJC87XHJcblx0dmFyIG5vb3AgPSBmdW5jdGlvbiAoKSB7fTtcclxuXHJcblx0Ly8gY2FjaGluZyBjb21tb25seSB1c2VkIHZhcmlhYmxlc1xyXG5cdHZhciAkZG9jdW1lbnQsICRsb2NhdGlvbiwgJHJlcXVlc3RBbmltYXRpb25GcmFtZSwgJGNhbmNlbEFuaW1hdGlvbkZyYW1lO1xyXG5cclxuXHQvLyBzZWxmIGludm9raW5nIGZ1bmN0aW9uIG5lZWRlZCBiZWNhdXNlIG9mIHRoZSB3YXkgbW9ja3Mgd29ya1xyXG5cdGZ1bmN0aW9uIGluaXRpYWxpemUod2luZG93KSB7XHJcblx0XHQkZG9jdW1lbnQgPSB3aW5kb3cuZG9jdW1lbnQ7XHJcblx0XHQkbG9jYXRpb24gPSB3aW5kb3cubG9jYXRpb247XHJcblx0XHQkY2FuY2VsQW5pbWF0aW9uRnJhbWUgPSB3aW5kb3cuY2FuY2VsQW5pbWF0aW9uRnJhbWUgfHwgd2luZG93LmNsZWFyVGltZW91dDtcclxuXHRcdCRyZXF1ZXN0QW5pbWF0aW9uRnJhbWUgPSB3aW5kb3cucmVxdWVzdEFuaW1hdGlvbkZyYW1lIHx8IHdpbmRvdy5zZXRUaW1lb3V0O1xyXG5cdH1cclxuXHJcblx0aW5pdGlhbGl6ZSh3aW5kb3cpO1xyXG5cclxuXHRtLnZlcnNpb24gPSBmdW5jdGlvbigpIHtcclxuXHRcdHJldHVybiBWRVJTSU9OO1xyXG5cdH07XHJcblxyXG5cdC8qKlxyXG5cdCAqIEB0eXBlZGVmIHtTdHJpbmd9IFRhZ1xyXG5cdCAqIEEgc3RyaW5nIHRoYXQgbG9va3MgbGlrZSAtPiBkaXYuY2xhc3NuYW1lI2lkW3BhcmFtPW9uZV1bcGFyYW0yPXR3b11cclxuXHQgKiBXaGljaCBkZXNjcmliZXMgYSBET00gbm9kZVxyXG5cdCAqL1xyXG5cclxuXHQvKipcclxuXHQgKlxyXG5cdCAqIEBwYXJhbSB7VGFnfSBUaGUgRE9NIG5vZGUgdGFnXHJcblx0ICogQHBhcmFtIHtPYmplY3Q9W119IG9wdGlvbmFsIGtleS12YWx1ZSBwYWlycyB0byBiZSBtYXBwZWQgdG8gRE9NIGF0dHJzXHJcblx0ICogQHBhcmFtIHsuLi5tTm9kZT1bXX0gWmVybyBvciBtb3JlIE1pdGhyaWwgY2hpbGQgbm9kZXMuIENhbiBiZSBhbiBhcnJheSwgb3Igc3BsYXQgKG9wdGlvbmFsKVxyXG5cdCAqXHJcblx0ICovXHJcblx0ZnVuY3Rpb24gbSh0YWcsIHBhaXJzKSB7XHJcblx0XHRmb3IgKHZhciBhcmdzID0gW10sIGkgPSAxOyBpIDwgYXJndW1lbnRzLmxlbmd0aDsgaSsrKSB7XHJcblx0XHRcdGFyZ3NbaSAtIDFdID0gYXJndW1lbnRzW2ldO1xyXG5cdFx0fVxyXG5cdFx0aWYgKGlzT2JqZWN0KHRhZykpIHJldHVybiBwYXJhbWV0ZXJpemUodGFnLCBhcmdzKTtcclxuXHRcdHZhciBoYXNBdHRycyA9IHBhaXJzICE9IG51bGwgJiYgaXNPYmplY3QocGFpcnMpICYmICEoXCJ0YWdcIiBpbiBwYWlycyB8fCBcInZpZXdcIiBpbiBwYWlycyB8fCBcInN1YnRyZWVcIiBpbiBwYWlycyk7XHJcblx0XHR2YXIgYXR0cnMgPSBoYXNBdHRycyA/IHBhaXJzIDoge307XHJcblx0XHR2YXIgY2xhc3NBdHRyTmFtZSA9IFwiY2xhc3NcIiBpbiBhdHRycyA/IFwiY2xhc3NcIiA6IFwiY2xhc3NOYW1lXCI7XHJcblx0XHR2YXIgY2VsbCA9IHt0YWc6IFwiZGl2XCIsIGF0dHJzOiB7fX07XHJcblx0XHR2YXIgbWF0Y2gsIGNsYXNzZXMgPSBbXTtcclxuXHRcdGlmICghaXNTdHJpbmcodGFnKSkgdGhyb3cgbmV3IEVycm9yKFwic2VsZWN0b3IgaW4gbShzZWxlY3RvciwgYXR0cnMsIGNoaWxkcmVuKSBzaG91bGQgYmUgYSBzdHJpbmdcIik7XHJcblx0XHR3aGlsZSAoKG1hdGNoID0gcGFyc2VyLmV4ZWModGFnKSkgIT0gbnVsbCkge1xyXG5cdFx0XHRpZiAobWF0Y2hbMV0gPT09IFwiXCIgJiYgbWF0Y2hbMl0pIGNlbGwudGFnID0gbWF0Y2hbMl07XHJcblx0XHRcdGVsc2UgaWYgKG1hdGNoWzFdID09PSBcIiNcIikgY2VsbC5hdHRycy5pZCA9IG1hdGNoWzJdO1xyXG5cdFx0XHRlbHNlIGlmIChtYXRjaFsxXSA9PT0gXCIuXCIpIGNsYXNzZXMucHVzaChtYXRjaFsyXSk7XHJcblx0XHRcdGVsc2UgaWYgKG1hdGNoWzNdWzBdID09PSBcIltcIikge1xyXG5cdFx0XHRcdHZhciBwYWlyID0gYXR0clBhcnNlci5leGVjKG1hdGNoWzNdKTtcclxuXHRcdFx0XHRjZWxsLmF0dHJzW3BhaXJbMV1dID0gcGFpclszXSB8fCAocGFpclsyXSA/IFwiXCIgOnRydWUpO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblxyXG5cdFx0dmFyIGNoaWxkcmVuID0gaGFzQXR0cnMgPyBhcmdzLnNsaWNlKDEpIDogYXJncztcclxuXHRcdGlmIChjaGlsZHJlbi5sZW5ndGggPT09IDEgJiYgaXNBcnJheShjaGlsZHJlblswXSkpIHtcclxuXHRcdFx0Y2VsbC5jaGlsZHJlbiA9IGNoaWxkcmVuWzBdO1xyXG5cdFx0fVxyXG5cdFx0ZWxzZSB7XHJcblx0XHRcdGNlbGwuY2hpbGRyZW4gPSBjaGlsZHJlbjtcclxuXHRcdH1cclxuXHJcblx0XHRmb3IgKHZhciBhdHRyTmFtZSBpbiBhdHRycykge1xyXG5cdFx0XHRpZiAoYXR0cnMuaGFzT3duUHJvcGVydHkoYXR0ck5hbWUpKSB7XHJcblx0XHRcdFx0aWYgKGF0dHJOYW1lID09PSBjbGFzc0F0dHJOYW1lICYmIGF0dHJzW2F0dHJOYW1lXSAhPSBudWxsICYmIGF0dHJzW2F0dHJOYW1lXSAhPT0gXCJcIikge1xyXG5cdFx0XHRcdFx0Y2xhc3Nlcy5wdXNoKGF0dHJzW2F0dHJOYW1lXSk7XHJcblx0XHRcdFx0XHRjZWxsLmF0dHJzW2F0dHJOYW1lXSA9IFwiXCI7IC8vY3JlYXRlIGtleSBpbiBjb3JyZWN0IGl0ZXJhdGlvbiBvcmRlclxyXG5cdFx0XHRcdH1cclxuXHRcdFx0XHRlbHNlIGNlbGwuYXR0cnNbYXR0ck5hbWVdID0gYXR0cnNbYXR0ck5hbWVdO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblx0XHRpZiAoY2xhc3Nlcy5sZW5ndGgpIGNlbGwuYXR0cnNbY2xhc3NBdHRyTmFtZV0gPSBjbGFzc2VzLmpvaW4oXCIgXCIpO1xyXG5cclxuXHRcdHJldHVybiBjZWxsO1xyXG5cdH1cclxuXHRmdW5jdGlvbiBmb3JFYWNoKGxpc3QsIGYpIHtcclxuXHRcdGZvciAodmFyIGkgPSAwOyBpIDwgbGlzdC5sZW5ndGggJiYgIWYobGlzdFtpXSwgaSsrKTspIHt9XHJcblx0fVxyXG5cdGZ1bmN0aW9uIGZvcktleXMobGlzdCwgZikge1xyXG5cdFx0Zm9yRWFjaChsaXN0LCBmdW5jdGlvbiAoYXR0cnMsIGkpIHtcclxuXHRcdFx0cmV0dXJuIChhdHRycyA9IGF0dHJzICYmIGF0dHJzLmF0dHJzKSAmJiBhdHRycy5rZXkgIT0gbnVsbCAmJiBmKGF0dHJzLCBpKTtcclxuXHRcdH0pO1xyXG5cdH1cclxuXHQvLyBUaGlzIGZ1bmN0aW9uIHdhcyBjYXVzaW5nIGRlb3B0cyBpbiBDaHJvbWUuXHJcblx0Ly8gV2VsbCBubyBsb25nZXJcclxuXHRmdW5jdGlvbiBkYXRhVG9TdHJpbmcoZGF0YSkge1xyXG4gICAgaWYgKGRhdGEgPT0gbnVsbCkgcmV0dXJuICcnO1xyXG4gICAgaWYgKHR5cGVvZiBkYXRhID09PSAnb2JqZWN0JykgcmV0dXJuIGRhdGE7XHJcbiAgICBpZiAoZGF0YS50b1N0cmluZygpID09IG51bGwpIHJldHVybiBcIlwiOyAvLyBwcmV2ZW50IHJlY3Vyc2lvbiBlcnJvciBvbiBGRlxyXG4gICAgcmV0dXJuIGRhdGE7XHJcblx0fVxyXG5cdC8vIFRoaXMgZnVuY3Rpb24gd2FzIGNhdXNpbmcgZGVvcHRzIGluIENocm9tZS5cclxuXHRmdW5jdGlvbiBpbmplY3RUZXh0Tm9kZShwYXJlbnRFbGVtZW50LCBmaXJzdCwgaW5kZXgsIGRhdGEpIHtcclxuXHRcdHRyeSB7XHJcblx0XHRcdGluc2VydE5vZGUocGFyZW50RWxlbWVudCwgZmlyc3QsIGluZGV4KTtcclxuXHRcdFx0Zmlyc3Qubm9kZVZhbHVlID0gZGF0YTtcclxuXHRcdH0gY2F0Y2ggKGUpIHt9IC8vSUUgZXJyb25lb3VzbHkgdGhyb3dzIGVycm9yIHdoZW4gYXBwZW5kaW5nIGFuIGVtcHR5IHRleHQgbm9kZSBhZnRlciBhIG51bGxcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGZsYXR0ZW4obGlzdCkge1xyXG5cdFx0Ly9yZWN1cnNpdmVseSBmbGF0dGVuIGFycmF5XHJcblx0XHRmb3IgKHZhciBpID0gMDsgaSA8IGxpc3QubGVuZ3RoOyBpKyspIHtcclxuXHRcdFx0aWYgKGlzQXJyYXkobGlzdFtpXSkpIHtcclxuXHRcdFx0XHRsaXN0ID0gbGlzdC5jb25jYXQuYXBwbHkoW10sIGxpc3QpO1xyXG5cdFx0XHRcdC8vY2hlY2sgY3VycmVudCBpbmRleCBhZ2FpbiBhbmQgZmxhdHRlbiB1bnRpbCB0aGVyZSBhcmUgbm8gbW9yZSBuZXN0ZWQgYXJyYXlzIGF0IHRoYXQgaW5kZXhcclxuXHRcdFx0XHRpLS07XHJcblx0XHRcdH1cclxuXHRcdH1cclxuXHRcdHJldHVybiBsaXN0O1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gaW5zZXJ0Tm9kZShwYXJlbnRFbGVtZW50LCBub2RlLCBpbmRleCkge1xyXG5cdFx0cGFyZW50RWxlbWVudC5pbnNlcnRCZWZvcmUobm9kZSwgcGFyZW50RWxlbWVudC5jaGlsZE5vZGVzW2luZGV4XSB8fCBudWxsKTtcclxuXHR9XHJcblxyXG5cdHZhciBERUxFVElPTiA9IDEsIElOU0VSVElPTiA9IDIsIE1PVkUgPSAzO1xyXG5cclxuXHRmdW5jdGlvbiBoYW5kbGVLZXlzRGlmZmVyKGRhdGEsIGV4aXN0aW5nLCBjYWNoZWQsIHBhcmVudEVsZW1lbnQpIHtcclxuXHRcdGZvcktleXMoZGF0YSwgZnVuY3Rpb24gKGtleSwgaSkge1xyXG5cdFx0XHRleGlzdGluZ1trZXkgPSBrZXkua2V5XSA9IGV4aXN0aW5nW2tleV0gPyB7XHJcblx0XHRcdFx0YWN0aW9uOiBNT1ZFLFxyXG5cdFx0XHRcdGluZGV4OiBpLFxyXG5cdFx0XHRcdGZyb206IGV4aXN0aW5nW2tleV0uaW5kZXgsXHJcblx0XHRcdFx0ZWxlbWVudDogY2FjaGVkLm5vZGVzW2V4aXN0aW5nW2tleV0uaW5kZXhdIHx8ICRkb2N1bWVudC5jcmVhdGVFbGVtZW50KFwiZGl2XCIpXHJcblx0XHRcdH0gOiB7YWN0aW9uOiBJTlNFUlRJT04sIGluZGV4OiBpfTtcclxuXHRcdH0pO1xyXG5cdFx0dmFyIGFjdGlvbnMgPSBbXTtcclxuXHRcdGZvciAodmFyIHByb3AgaW4gZXhpc3RpbmcpIGFjdGlvbnMucHVzaChleGlzdGluZ1twcm9wXSk7XHJcblx0XHR2YXIgY2hhbmdlcyA9IGFjdGlvbnMuc29ydChzb3J0Q2hhbmdlcyksIG5ld0NhY2hlZCA9IG5ldyBBcnJheShjYWNoZWQubGVuZ3RoKTtcclxuXHRcdG5ld0NhY2hlZC5ub2RlcyA9IGNhY2hlZC5ub2Rlcy5zbGljZSgpO1xyXG5cclxuXHRcdGZvckVhY2goY2hhbmdlcywgZnVuY3Rpb24gKGNoYW5nZSkge1xyXG5cdFx0XHR2YXIgaW5kZXggPSBjaGFuZ2UuaW5kZXg7XHJcblx0XHRcdGlmIChjaGFuZ2UuYWN0aW9uID09PSBERUxFVElPTikge1xyXG5cdFx0XHRcdGNsZWFyKGNhY2hlZFtpbmRleF0ubm9kZXMsIGNhY2hlZFtpbmRleF0pO1xyXG5cdFx0XHRcdG5ld0NhY2hlZC5zcGxpY2UoaW5kZXgsIDEpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGlmIChjaGFuZ2UuYWN0aW9uID09PSBJTlNFUlRJT04pIHtcclxuXHRcdFx0XHR2YXIgZHVtbXkgPSAkZG9jdW1lbnQuY3JlYXRlRWxlbWVudChcImRpdlwiKTtcclxuXHRcdFx0XHRkdW1teS5rZXkgPSBkYXRhW2luZGV4XS5hdHRycy5rZXk7XHJcblx0XHRcdFx0aW5zZXJ0Tm9kZShwYXJlbnRFbGVtZW50LCBkdW1teSwgaW5kZXgpO1xyXG5cdFx0XHRcdG5ld0NhY2hlZC5zcGxpY2UoaW5kZXgsIDAsIHtcclxuXHRcdFx0XHRcdGF0dHJzOiB7a2V5OiBkYXRhW2luZGV4XS5hdHRycy5rZXl9LFxyXG5cdFx0XHRcdFx0bm9kZXM6IFtkdW1teV1cclxuXHRcdFx0XHR9KTtcclxuXHRcdFx0XHRuZXdDYWNoZWQubm9kZXNbaW5kZXhdID0gZHVtbXk7XHJcblx0XHRcdH1cclxuXHJcblx0XHRcdGlmIChjaGFuZ2UuYWN0aW9uID09PSBNT1ZFKSB7XHJcblx0XHRcdFx0dmFyIGNoYW5nZUVsZW1lbnQgPSBjaGFuZ2UuZWxlbWVudDtcclxuXHRcdFx0XHR2YXIgbWF5YmVDaGFuZ2VkID0gcGFyZW50RWxlbWVudC5jaGlsZE5vZGVzW2luZGV4XTtcclxuXHRcdFx0XHRpZiAobWF5YmVDaGFuZ2VkICE9PSBjaGFuZ2VFbGVtZW50ICYmIGNoYW5nZUVsZW1lbnQgIT09IG51bGwpIHtcclxuXHRcdFx0XHRcdHBhcmVudEVsZW1lbnQuaW5zZXJ0QmVmb3JlKGNoYW5nZUVsZW1lbnQsIG1heWJlQ2hhbmdlZCB8fCBudWxsKTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdFx0bmV3Q2FjaGVkW2luZGV4XSA9IGNhY2hlZFtjaGFuZ2UuZnJvbV07XHJcblx0XHRcdFx0bmV3Q2FjaGVkLm5vZGVzW2luZGV4XSA9IGNoYW5nZUVsZW1lbnQ7XHJcblx0XHRcdH1cclxuXHRcdH0pO1xyXG5cclxuXHRcdHJldHVybiBuZXdDYWNoZWQ7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBkaWZmS2V5cyhkYXRhLCBjYWNoZWQsIGV4aXN0aW5nLCBwYXJlbnRFbGVtZW50KSB7XHJcblx0XHR2YXIga2V5c0RpZmZlciA9IGRhdGEubGVuZ3RoICE9PSBjYWNoZWQubGVuZ3RoO1xyXG5cdFx0aWYgKCFrZXlzRGlmZmVyKSB7XHJcblx0XHRcdGZvcktleXMoZGF0YSwgZnVuY3Rpb24gKGF0dHJzLCBpKSB7XHJcblx0XHRcdFx0dmFyIGNhY2hlZENlbGwgPSBjYWNoZWRbaV07XHJcblx0XHRcdFx0cmV0dXJuIGtleXNEaWZmZXIgPSBjYWNoZWRDZWxsICYmIGNhY2hlZENlbGwuYXR0cnMgJiYgY2FjaGVkQ2VsbC5hdHRycy5rZXkgIT09IGF0dHJzLmtleTtcclxuXHRcdFx0fSk7XHJcblx0XHR9XHJcblxyXG5cdFx0cmV0dXJuIGtleXNEaWZmZXIgPyBoYW5kbGVLZXlzRGlmZmVyKGRhdGEsIGV4aXN0aW5nLCBjYWNoZWQsIHBhcmVudEVsZW1lbnQpIDogY2FjaGVkO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gZGlmZkFycmF5KGRhdGEsIGNhY2hlZCwgbm9kZXMpIHtcclxuXHRcdC8vZGlmZiB0aGUgYXJyYXkgaXRzZWxmXHJcblxyXG5cdFx0Ly91cGRhdGUgdGhlIGxpc3Qgb2YgRE9NIG5vZGVzIGJ5IGNvbGxlY3RpbmcgdGhlIG5vZGVzIGZyb20gZWFjaCBpdGVtXHJcblx0XHRmb3JFYWNoKGRhdGEsIGZ1bmN0aW9uIChfLCBpKSB7XHJcblx0XHRcdGlmIChjYWNoZWRbaV0gIT0gbnVsbCkgbm9kZXMucHVzaC5hcHBseShub2RlcywgY2FjaGVkW2ldLm5vZGVzKTtcclxuXHRcdH0pXHJcblx0XHQvL3JlbW92ZSBpdGVtcyBmcm9tIHRoZSBlbmQgb2YgdGhlIGFycmF5IGlmIHRoZSBuZXcgYXJyYXkgaXMgc2hvcnRlciB0aGFuIHRoZSBvbGQgb25lLiBpZiBlcnJvcnMgZXZlciBoYXBwZW4gaGVyZSwgdGhlIGlzc3VlIGlzIG1vc3QgbGlrZWx5XHJcblx0XHQvL2EgYnVnIGluIHRoZSBjb25zdHJ1Y3Rpb24gb2YgdGhlIGBjYWNoZWRgIGRhdGEgc3RydWN0dXJlIHNvbWV3aGVyZSBlYXJsaWVyIGluIHRoZSBwcm9ncmFtXHJcblx0XHRmb3JFYWNoKGNhY2hlZC5ub2RlcywgZnVuY3Rpb24gKG5vZGUsIGkpIHtcclxuXHRcdFx0aWYgKG5vZGUucGFyZW50Tm9kZSAhPSBudWxsICYmIG5vZGVzLmluZGV4T2Yobm9kZSkgPCAwKSBjbGVhcihbbm9kZV0sIFtjYWNoZWRbaV1dKTtcclxuXHRcdH0pXHJcblx0XHRpZiAoZGF0YS5sZW5ndGggPCBjYWNoZWQubGVuZ3RoKSBjYWNoZWQubGVuZ3RoID0gZGF0YS5sZW5ndGg7XHJcblx0XHRjYWNoZWQubm9kZXMgPSBub2RlcztcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGJ1aWxkQXJyYXlLZXlzKGRhdGEpIHtcclxuXHRcdHZhciBndWlkID0gMDtcclxuXHRcdGZvcktleXMoZGF0YSwgZnVuY3Rpb24gKCkge1xyXG5cdFx0XHRmb3JFYWNoKGRhdGEsIGZ1bmN0aW9uIChhdHRycykge1xyXG5cdFx0XHRcdGlmICgoYXR0cnMgPSBhdHRycyAmJiBhdHRycy5hdHRycykgJiYgYXR0cnMua2V5ID09IG51bGwpIGF0dHJzLmtleSA9IFwiX19taXRocmlsX19cIiArIGd1aWQrKztcclxuXHRcdFx0fSlcclxuXHRcdFx0cmV0dXJuIDE7XHJcblx0XHR9KTtcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIG1heWJlUmVjcmVhdGVPYmplY3QoZGF0YSwgY2FjaGVkLCBkYXRhQXR0cktleXMpIHtcclxuXHRcdC8vaWYgYW4gZWxlbWVudCBpcyBkaWZmZXJlbnQgZW5vdWdoIGZyb20gdGhlIG9uZSBpbiBjYWNoZSwgcmVjcmVhdGUgaXRcclxuXHRcdGlmIChkYXRhLnRhZyAhPT0gY2FjaGVkLnRhZyB8fFxyXG5cdFx0XHRcdGRhdGFBdHRyS2V5cy5zb3J0KCkuam9pbigpICE9PSBPYmplY3Qua2V5cyhjYWNoZWQuYXR0cnMpLnNvcnQoKS5qb2luKCkgfHxcclxuXHRcdFx0XHRkYXRhLmF0dHJzLmlkICE9PSBjYWNoZWQuYXR0cnMuaWQgfHxcclxuXHRcdFx0XHRkYXRhLmF0dHJzLmtleSAhPT0gY2FjaGVkLmF0dHJzLmtleSB8fFxyXG5cdFx0XHRcdChtLnJlZHJhdy5zdHJhdGVneSgpID09PSBcImFsbFwiICYmICghY2FjaGVkLmNvbmZpZ0NvbnRleHQgfHwgY2FjaGVkLmNvbmZpZ0NvbnRleHQucmV0YWluICE9PSB0cnVlKSkgfHxcclxuXHRcdFx0XHQobS5yZWRyYXcuc3RyYXRlZ3koKSA9PT0gXCJkaWZmXCIgJiYgY2FjaGVkLmNvbmZpZ0NvbnRleHQgJiYgY2FjaGVkLmNvbmZpZ0NvbnRleHQucmV0YWluID09PSBmYWxzZSkpIHtcclxuXHRcdFx0aWYgKGNhY2hlZC5ub2Rlcy5sZW5ndGgpIGNsZWFyKGNhY2hlZC5ub2Rlcyk7XHJcblx0XHRcdGlmIChjYWNoZWQuY29uZmlnQ29udGV4dCAmJiBpc0Z1bmN0aW9uKGNhY2hlZC5jb25maWdDb250ZXh0Lm9udW5sb2FkKSkgY2FjaGVkLmNvbmZpZ0NvbnRleHQub251bmxvYWQoKTtcclxuXHRcdFx0aWYgKGNhY2hlZC5jb250cm9sbGVycykge1xyXG5cdFx0XHRcdGZvckVhY2goY2FjaGVkLmNvbnRyb2xsZXJzLCBmdW5jdGlvbiAoY29udHJvbGxlcikge1xyXG5cdFx0XHRcdFx0aWYgKGNvbnRyb2xsZXIudW5sb2FkKSBjb250cm9sbGVyLm9udW5sb2FkKHtwcmV2ZW50RGVmYXVsdDogbm9vcH0pO1xyXG5cdFx0XHRcdH0pO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBnZXRPYmplY3ROYW1lc3BhY2UoZGF0YSwgbmFtZXNwYWNlKSB7XHJcblx0XHRyZXR1cm4gZGF0YS5hdHRycy54bWxucyA/IGRhdGEuYXR0cnMueG1sbnMgOlxyXG5cdFx0XHRkYXRhLnRhZyA9PT0gXCJzdmdcIiA/IFwiaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmdcIiA6XHJcblx0XHRcdGRhdGEudGFnID09PSBcIm1hdGhcIiA/IFwiaHR0cDovL3d3dy53My5vcmcvMTk5OC9NYXRoL01hdGhNTFwiIDpcclxuXHRcdFx0bmFtZXNwYWNlO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gdW5sb2FkQ2FjaGVkQ29udHJvbGxlcnMoY2FjaGVkLCB2aWV3cywgY29udHJvbGxlcnMpIHtcclxuXHRcdGlmIChjb250cm9sbGVycy5sZW5ndGgpIHtcclxuXHRcdFx0Y2FjaGVkLnZpZXdzID0gdmlld3M7XHJcblx0XHRcdGNhY2hlZC5jb250cm9sbGVycyA9IGNvbnRyb2xsZXJzO1xyXG5cdFx0XHRmb3JFYWNoKGNvbnRyb2xsZXJzLCBmdW5jdGlvbiAoY29udHJvbGxlcikge1xyXG5cdFx0XHRcdGlmIChjb250cm9sbGVyLm9udW5sb2FkICYmIGNvbnRyb2xsZXIub251bmxvYWQuJG9sZCkgY29udHJvbGxlci5vbnVubG9hZCA9IGNvbnRyb2xsZXIub251bmxvYWQuJG9sZDtcclxuXHRcdFx0XHRpZiAocGVuZGluZ1JlcXVlc3RzICYmIGNvbnRyb2xsZXIub251bmxvYWQpIHtcclxuXHRcdFx0XHRcdHZhciBvbnVubG9hZCA9IGNvbnRyb2xsZXIub251bmxvYWQ7XHJcblx0XHRcdFx0XHRjb250cm9sbGVyLm9udW5sb2FkID0gbm9vcDtcclxuXHRcdFx0XHRcdGNvbnRyb2xsZXIub251bmxvYWQuJG9sZCA9IG9udW5sb2FkO1xyXG5cdFx0XHRcdH1cclxuXHRcdFx0fSk7XHJcblx0XHR9XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBzY2hlZHVsZUNvbmZpZ3NUb0JlQ2FsbGVkKGNvbmZpZ3MsIGRhdGEsIG5vZGUsIGlzTmV3LCBjYWNoZWQpIHtcclxuXHRcdC8vc2NoZWR1bGUgY29uZmlncyB0byBiZSBjYWxsZWQuIFRoZXkgYXJlIGNhbGxlZCBhZnRlciBgYnVpbGRgXHJcblx0XHQvL2ZpbmlzaGVzIHJ1bm5pbmdcclxuXHRcdGlmIChpc0Z1bmN0aW9uKGRhdGEuYXR0cnMuY29uZmlnKSkge1xyXG5cdFx0XHR2YXIgY29udGV4dCA9IGNhY2hlZC5jb25maWdDb250ZXh0ID0gY2FjaGVkLmNvbmZpZ0NvbnRleHQgfHwge307XHJcblxyXG5cdFx0XHQvL2JpbmRcclxuXHRcdFx0Y29uZmlncy5wdXNoKGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRcdHJldHVybiBkYXRhLmF0dHJzLmNvbmZpZy5jYWxsKGRhdGEsIG5vZGUsICFpc05ldywgY29udGV4dCwgY2FjaGVkKTtcclxuXHRcdFx0fSk7XHJcblx0XHR9XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBidWlsZFVwZGF0ZWROb2RlKGNhY2hlZCwgZGF0YSwgZWRpdGFibGUsIGhhc0tleXMsIG5hbWVzcGFjZSwgdmlld3MsIGNvbmZpZ3MsIGNvbnRyb2xsZXJzKSB7XHJcblx0XHR2YXIgbm9kZSA9IGNhY2hlZC5ub2Rlc1swXTtcclxuXHRcdGlmIChoYXNLZXlzKSBzZXRBdHRyaWJ1dGVzKG5vZGUsIGRhdGEudGFnLCBkYXRhLmF0dHJzLCBjYWNoZWQuYXR0cnMsIG5hbWVzcGFjZSk7XHJcblx0XHRjYWNoZWQuY2hpbGRyZW4gPSBidWlsZChub2RlLCBkYXRhLnRhZywgdW5kZWZpbmVkLCB1bmRlZmluZWQsIGRhdGEuY2hpbGRyZW4sIGNhY2hlZC5jaGlsZHJlbiwgZmFsc2UsIDAsIGRhdGEuYXR0cnMuY29udGVudGVkaXRhYmxlID8gbm9kZSA6IGVkaXRhYmxlLCBuYW1lc3BhY2UsIGNvbmZpZ3MpO1xyXG5cdFx0Y2FjaGVkLm5vZGVzLmludGFjdCA9IHRydWU7XHJcblxyXG5cdFx0aWYgKGNvbnRyb2xsZXJzLmxlbmd0aCkge1xyXG5cdFx0XHRjYWNoZWQudmlld3MgPSB2aWV3cztcclxuXHRcdFx0Y2FjaGVkLmNvbnRyb2xsZXJzID0gY29udHJvbGxlcnM7XHJcblx0XHR9XHJcblxyXG5cdFx0cmV0dXJuIG5vZGU7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBoYW5kbGVOb25leGlzdGVudE5vZGVzKGRhdGEsIHBhcmVudEVsZW1lbnQsIGluZGV4KSB7XHJcblx0XHR2YXIgbm9kZXM7XHJcblx0XHRpZiAoZGF0YS4kdHJ1c3RlZCkge1xyXG5cdFx0XHRub2RlcyA9IGluamVjdEhUTUwocGFyZW50RWxlbWVudCwgaW5kZXgsIGRhdGEpO1xyXG5cdFx0fVxyXG5cdFx0ZWxzZSB7XHJcblx0XHRcdG5vZGVzID0gWyRkb2N1bWVudC5jcmVhdGVUZXh0Tm9kZShkYXRhKV07XHJcblx0XHRcdGlmICghcGFyZW50RWxlbWVudC5ub2RlTmFtZS5tYXRjaCh2b2lkRWxlbWVudHMpKSBpbnNlcnROb2RlKHBhcmVudEVsZW1lbnQsIG5vZGVzWzBdLCBpbmRleCk7XHJcblx0XHR9XHJcblxyXG5cdFx0dmFyIGNhY2hlZCA9IHR5cGVvZiBkYXRhID09PSBcInN0cmluZ1wiIHx8IHR5cGVvZiBkYXRhID09PSBcIm51bWJlclwiIHx8IHR5cGVvZiBkYXRhID09PSBcImJvb2xlYW5cIiA/IG5ldyBkYXRhLmNvbnN0cnVjdG9yKGRhdGEpIDogZGF0YTtcclxuXHRcdGNhY2hlZC5ub2RlcyA9IG5vZGVzO1xyXG5cdFx0cmV0dXJuIGNhY2hlZDtcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIHJlYXR0YWNoTm9kZXMoZGF0YSwgY2FjaGVkLCBwYXJlbnRFbGVtZW50LCBlZGl0YWJsZSwgaW5kZXgsIHBhcmVudFRhZykge1xyXG5cdFx0dmFyIG5vZGVzID0gY2FjaGVkLm5vZGVzO1xyXG5cdFx0aWYgKCFlZGl0YWJsZSB8fCBlZGl0YWJsZSAhPT0gJGRvY3VtZW50LmFjdGl2ZUVsZW1lbnQpIHtcclxuXHRcdFx0aWYgKGRhdGEuJHRydXN0ZWQpIHtcclxuXHRcdFx0XHRjbGVhcihub2RlcywgY2FjaGVkKTtcclxuXHRcdFx0XHRub2RlcyA9IGluamVjdEhUTUwocGFyZW50RWxlbWVudCwgaW5kZXgsIGRhdGEpO1xyXG5cdFx0XHR9XHJcblx0XHRcdC8vY29ybmVyIGNhc2U6IHJlcGxhY2luZyB0aGUgbm9kZVZhbHVlIG9mIGEgdGV4dCBub2RlIHRoYXQgaXMgYSBjaGlsZCBvZiBhIHRleHRhcmVhL2NvbnRlbnRlZGl0YWJsZSBkb2Vzbid0IHdvcmtcclxuXHRcdFx0Ly93ZSBuZWVkIHRvIHVwZGF0ZSB0aGUgdmFsdWUgcHJvcGVydHkgb2YgdGhlIHBhcmVudCB0ZXh0YXJlYSBvciB0aGUgaW5uZXJIVE1MIG9mIHRoZSBjb250ZW50ZWRpdGFibGUgZWxlbWVudCBpbnN0ZWFkXHJcblx0XHRcdGVsc2UgaWYgKHBhcmVudFRhZyA9PT0gXCJ0ZXh0YXJlYVwiKSB7XHJcblx0XHRcdFx0cGFyZW50RWxlbWVudC52YWx1ZSA9IGRhdGE7XHJcblx0XHRcdH1cclxuXHRcdFx0ZWxzZSBpZiAoZWRpdGFibGUpIHtcclxuXHRcdFx0XHRlZGl0YWJsZS5pbm5lckhUTUwgPSBkYXRhO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2Uge1xyXG5cdFx0XHRcdC8vd2FzIGEgdHJ1c3RlZCBzdHJpbmdcclxuXHRcdFx0XHRpZiAobm9kZXNbMF0ubm9kZVR5cGUgPT09IDEgfHwgbm9kZXMubGVuZ3RoID4gMSkge1xyXG5cdFx0XHRcdFx0Y2xlYXIoY2FjaGVkLm5vZGVzLCBjYWNoZWQpO1xyXG5cdFx0XHRcdFx0bm9kZXMgPSBbJGRvY3VtZW50LmNyZWF0ZVRleHROb2RlKGRhdGEpXTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdFx0aW5qZWN0VGV4dE5vZGUocGFyZW50RWxlbWVudCwgbm9kZXNbMF0sIGluZGV4LCBkYXRhKTtcclxuXHRcdFx0fVxyXG5cdFx0fVxyXG5cdFx0Y2FjaGVkID0gbmV3IGRhdGEuY29uc3RydWN0b3IoZGF0YSk7XHJcblx0XHRjYWNoZWQubm9kZXMgPSBub2RlcztcclxuXHRcdHJldHVybiBjYWNoZWQ7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBoYW5kbGVUZXh0KGNhY2hlZCwgZGF0YSwgaW5kZXgsIHBhcmVudEVsZW1lbnQsIHNob3VsZFJlYXR0YWNoLCBlZGl0YWJsZSwgcGFyZW50VGFnKSB7XHJcblx0XHQvL2hhbmRsZSB0ZXh0IG5vZGVzXHJcblx0XHRyZXR1cm4gY2FjaGVkLm5vZGVzLmxlbmd0aCA9PT0gMCA/IGhhbmRsZU5vbmV4aXN0ZW50Tm9kZXMoZGF0YSwgcGFyZW50RWxlbWVudCwgaW5kZXgpIDpcclxuXHRcdFx0Y2FjaGVkLnZhbHVlT2YoKSAhPT0gZGF0YS52YWx1ZU9mKCkgfHwgc2hvdWxkUmVhdHRhY2ggPT09IHRydWUgP1xyXG5cdFx0XHRcdHJlYXR0YWNoTm9kZXMoZGF0YSwgY2FjaGVkLCBwYXJlbnRFbGVtZW50LCBlZGl0YWJsZSwgaW5kZXgsIHBhcmVudFRhZykgOlxyXG5cdFx0XHQoY2FjaGVkLm5vZGVzLmludGFjdCA9IHRydWUsIGNhY2hlZCk7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBnZXRTdWJBcnJheUNvdW50KGl0ZW0pIHtcclxuXHRcdGlmIChpdGVtLiR0cnVzdGVkKSB7XHJcblx0XHRcdC8vZml4IG9mZnNldCBvZiBuZXh0IGVsZW1lbnQgaWYgaXRlbSB3YXMgYSB0cnVzdGVkIHN0cmluZyB3LyBtb3JlIHRoYW4gb25lIGh0bWwgZWxlbWVudFxyXG5cdFx0XHQvL3RoZSBmaXJzdCBjbGF1c2UgaW4gdGhlIHJlZ2V4cCBtYXRjaGVzIGVsZW1lbnRzXHJcblx0XHRcdC8vdGhlIHNlY29uZCBjbGF1c2UgKGFmdGVyIHRoZSBwaXBlKSBtYXRjaGVzIHRleHQgbm9kZXNcclxuXHRcdFx0dmFyIG1hdGNoID0gaXRlbS5tYXRjaCgvPFteXFwvXXxcXD5cXHMqW148XS9nKTtcclxuXHRcdFx0aWYgKG1hdGNoICE9IG51bGwpIHJldHVybiBtYXRjaC5sZW5ndGg7XHJcblx0XHR9XHJcblx0XHRlbHNlIGlmIChpc0FycmF5KGl0ZW0pKSB7XHJcblx0XHRcdHJldHVybiBpdGVtLmxlbmd0aDtcclxuXHRcdH1cclxuXHRcdHJldHVybiAxO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gYnVpbGRBcnJheShkYXRhLCBjYWNoZWQsIHBhcmVudEVsZW1lbnQsIGluZGV4LCBwYXJlbnRUYWcsIHNob3VsZFJlYXR0YWNoLCBlZGl0YWJsZSwgbmFtZXNwYWNlLCBjb25maWdzKSB7XHJcblx0XHRkYXRhID0gZmxhdHRlbihkYXRhKTtcclxuXHRcdHZhciBub2RlcyA9IFtdLCBpbnRhY3QgPSBjYWNoZWQubGVuZ3RoID09PSBkYXRhLmxlbmd0aCwgc3ViQXJyYXlDb3VudCA9IDA7XHJcblxyXG5cdFx0Ly9rZXlzIGFsZ29yaXRobTogc29ydCBlbGVtZW50cyB3aXRob3V0IHJlY3JlYXRpbmcgdGhlbSBpZiBrZXlzIGFyZSBwcmVzZW50XHJcblx0XHQvLzEpIGNyZWF0ZSBhIG1hcCBvZiBhbGwgZXhpc3Rpbmcga2V5cywgYW5kIG1hcmsgYWxsIGZvciBkZWxldGlvblxyXG5cdFx0Ly8yKSBhZGQgbmV3IGtleXMgdG8gbWFwIGFuZCBtYXJrIHRoZW0gZm9yIGFkZGl0aW9uXHJcblx0XHQvLzMpIGlmIGtleSBleGlzdHMgaW4gbmV3IGxpc3QsIGNoYW5nZSBhY3Rpb24gZnJvbSBkZWxldGlvbiB0byBhIG1vdmVcclxuXHRcdC8vNCkgZm9yIGVhY2gga2V5LCBoYW5kbGUgaXRzIGNvcnJlc3BvbmRpbmcgYWN0aW9uIGFzIG1hcmtlZCBpbiBwcmV2aW91cyBzdGVwc1xyXG5cdFx0dmFyIGV4aXN0aW5nID0ge30sIHNob3VsZE1haW50YWluSWRlbnRpdGllcyA9IGZhbHNlO1xyXG5cdFx0Zm9yS2V5cyhjYWNoZWQsIGZ1bmN0aW9uIChhdHRycywgaSkge1xyXG5cdFx0XHRzaG91bGRNYWludGFpbklkZW50aXRpZXMgPSB0cnVlO1xyXG5cdFx0XHRleGlzdGluZ1tjYWNoZWRbaV0uYXR0cnMua2V5XSA9IHthY3Rpb246IERFTEVUSU9OLCBpbmRleDogaX07XHJcblx0XHR9KTtcclxuXHJcblx0XHRidWlsZEFycmF5S2V5cyhkYXRhKTtcclxuXHRcdGlmIChzaG91bGRNYWludGFpbklkZW50aXRpZXMpIGNhY2hlZCA9IGRpZmZLZXlzKGRhdGEsIGNhY2hlZCwgZXhpc3RpbmcsIHBhcmVudEVsZW1lbnQpO1xyXG5cdFx0Ly9lbmQga2V5IGFsZ29yaXRobVxyXG5cclxuXHRcdHZhciBjYWNoZUNvdW50ID0gMDtcclxuXHRcdC8vZmFzdGVyIGV4cGxpY2l0bHkgd3JpdHRlblxyXG5cdFx0Zm9yICh2YXIgaSA9IDAsIGxlbiA9IGRhdGEubGVuZ3RoOyBpIDwgbGVuOyBpKyspIHtcclxuXHRcdFx0Ly9kaWZmIGVhY2ggaXRlbSBpbiB0aGUgYXJyYXlcclxuXHRcdFx0dmFyIGl0ZW0gPSBidWlsZChwYXJlbnRFbGVtZW50LCBwYXJlbnRUYWcsIGNhY2hlZCwgaW5kZXgsIGRhdGFbaV0sIGNhY2hlZFtjYWNoZUNvdW50XSwgc2hvdWxkUmVhdHRhY2gsIGluZGV4ICsgc3ViQXJyYXlDb3VudCB8fCBzdWJBcnJheUNvdW50LCBlZGl0YWJsZSwgbmFtZXNwYWNlLCBjb25maWdzKTtcclxuXHJcblx0XHRcdGlmIChpdGVtICE9PSB1bmRlZmluZWQpIHtcclxuXHRcdFx0XHRpbnRhY3QgPSBpbnRhY3QgJiYgaXRlbS5ub2Rlcy5pbnRhY3Q7XHJcblx0XHRcdFx0c3ViQXJyYXlDb3VudCArPSBnZXRTdWJBcnJheUNvdW50KGl0ZW0pO1xyXG5cdFx0XHRcdGNhY2hlZFtjYWNoZUNvdW50KytdID0gaXRlbTtcclxuXHRcdFx0fVxyXG5cdFx0fVxyXG5cclxuXHRcdGlmICghaW50YWN0KSBkaWZmQXJyYXkoZGF0YSwgY2FjaGVkLCBub2Rlcyk7XHJcblx0XHRyZXR1cm4gY2FjaGVkXHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBtYWtlQ2FjaGUoZGF0YSwgY2FjaGVkLCBpbmRleCwgcGFyZW50SW5kZXgsIHBhcmVudENhY2hlKSB7XHJcblx0XHRpZiAoY2FjaGVkICE9IG51bGwpIHtcclxuXHRcdFx0aWYgKHR5cGUuY2FsbChjYWNoZWQpID09PSB0eXBlLmNhbGwoZGF0YSkpIHJldHVybiBjYWNoZWQ7XHJcblxyXG5cdFx0XHRpZiAocGFyZW50Q2FjaGUgJiYgcGFyZW50Q2FjaGUubm9kZXMpIHtcclxuXHRcdFx0XHR2YXIgb2Zmc2V0ID0gaW5kZXggLSBwYXJlbnRJbmRleCwgZW5kID0gb2Zmc2V0ICsgKGlzQXJyYXkoZGF0YSkgPyBkYXRhIDogY2FjaGVkLm5vZGVzKS5sZW5ndGg7XHJcblx0XHRcdFx0Y2xlYXIocGFyZW50Q2FjaGUubm9kZXMuc2xpY2Uob2Zmc2V0LCBlbmQpLCBwYXJlbnRDYWNoZS5zbGljZShvZmZzZXQsIGVuZCkpO1xyXG5cdFx0XHR9IGVsc2UgaWYgKGNhY2hlZC5ub2Rlcykge1xyXG5cdFx0XHRcdGNsZWFyKGNhY2hlZC5ub2RlcywgY2FjaGVkKTtcclxuXHRcdFx0fVxyXG5cdFx0fVxyXG5cclxuXHRcdGNhY2hlZCA9IG5ldyBkYXRhLmNvbnN0cnVjdG9yKCk7XHJcblx0XHQvL2lmIGNvbnN0cnVjdG9yIGNyZWF0ZXMgYSB2aXJ0dWFsIGRvbSBlbGVtZW50LCB1c2UgYSBibGFuayBvYmplY3RcclxuXHRcdC8vYXMgdGhlIGJhc2UgY2FjaGVkIG5vZGUgaW5zdGVhZCBvZiBjb3B5aW5nIHRoZSB2aXJ0dWFsIGVsICgjMjc3KVxyXG5cdFx0aWYgKGNhY2hlZC50YWcpIGNhY2hlZCA9IHt9O1xyXG5cdFx0Y2FjaGVkLm5vZGVzID0gW107XHJcblx0XHRyZXR1cm4gY2FjaGVkO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gY29uc3RydWN0Tm9kZShkYXRhLCBuYW1lc3BhY2UpIHtcclxuXHRcdHJldHVybiBuYW1lc3BhY2UgPT09IHVuZGVmaW5lZCA/XHJcblx0XHRcdGRhdGEuYXR0cnMuaXMgPyAkZG9jdW1lbnQuY3JlYXRlRWxlbWVudChkYXRhLnRhZywgZGF0YS5hdHRycy5pcykgOiAkZG9jdW1lbnQuY3JlYXRlRWxlbWVudChkYXRhLnRhZykgOlxyXG5cdFx0XHRkYXRhLmF0dHJzLmlzID8gJGRvY3VtZW50LmNyZWF0ZUVsZW1lbnROUyhuYW1lc3BhY2UsIGRhdGEudGFnLCBkYXRhLmF0dHJzLmlzKSA6ICRkb2N1bWVudC5jcmVhdGVFbGVtZW50TlMobmFtZXNwYWNlLCBkYXRhLnRhZyk7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBjb25zdHJ1Y3RBdHRycyhkYXRhLCBub2RlLCBuYW1lc3BhY2UsIGhhc0tleXMpIHtcclxuXHRcdHJldHVybiBoYXNLZXlzID8gc2V0QXR0cmlidXRlcyhub2RlLCBkYXRhLnRhZywgZGF0YS5hdHRycywge30sIG5hbWVzcGFjZSkgOiBkYXRhLmF0dHJzO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gY29uc3RydWN0Q2hpbGRyZW4oZGF0YSwgbm9kZSwgY2FjaGVkLCBlZGl0YWJsZSwgbmFtZXNwYWNlLCBjb25maWdzKSB7XHJcblx0XHRyZXR1cm4gZGF0YS5jaGlsZHJlbiAhPSBudWxsICYmIGRhdGEuY2hpbGRyZW4ubGVuZ3RoID4gMCA/XHJcblx0XHRcdGJ1aWxkKG5vZGUsIGRhdGEudGFnLCB1bmRlZmluZWQsIHVuZGVmaW5lZCwgZGF0YS5jaGlsZHJlbiwgY2FjaGVkLmNoaWxkcmVuLCB0cnVlLCAwLCBkYXRhLmF0dHJzLmNvbnRlbnRlZGl0YWJsZSA/IG5vZGUgOiBlZGl0YWJsZSwgbmFtZXNwYWNlLCBjb25maWdzKSA6XHJcblx0XHRcdGRhdGEuY2hpbGRyZW47XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiByZWNvbnN0cnVjdENhY2hlZChkYXRhLCBhdHRycywgY2hpbGRyZW4sIG5vZGUsIG5hbWVzcGFjZSwgdmlld3MsIGNvbnRyb2xsZXJzKSB7XHJcblx0XHR2YXIgY2FjaGVkID0ge3RhZzogZGF0YS50YWcsIGF0dHJzOiBhdHRycywgY2hpbGRyZW46IGNoaWxkcmVuLCBub2RlczogW25vZGVdfTtcclxuXHRcdHVubG9hZENhY2hlZENvbnRyb2xsZXJzKGNhY2hlZCwgdmlld3MsIGNvbnRyb2xsZXJzKTtcclxuXHRcdGlmIChjYWNoZWQuY2hpbGRyZW4gJiYgIWNhY2hlZC5jaGlsZHJlbi5ub2RlcykgY2FjaGVkLmNoaWxkcmVuLm5vZGVzID0gW107XHJcblx0XHQvL2VkZ2UgY2FzZTogc2V0dGluZyB2YWx1ZSBvbiA8c2VsZWN0PiBkb2Vzbid0IHdvcmsgYmVmb3JlIGNoaWxkcmVuIGV4aXN0LCBzbyBzZXQgaXQgYWdhaW4gYWZ0ZXIgY2hpbGRyZW4gaGF2ZSBiZWVuIGNyZWF0ZWRcclxuXHRcdGlmIChkYXRhLnRhZyA9PT0gXCJzZWxlY3RcIiAmJiBcInZhbHVlXCIgaW4gZGF0YS5hdHRycykgc2V0QXR0cmlidXRlcyhub2RlLCBkYXRhLnRhZywge3ZhbHVlOiBkYXRhLmF0dHJzLnZhbHVlfSwge30sIG5hbWVzcGFjZSk7XHJcblx0XHRyZXR1cm4gY2FjaGVkXHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBnZXRDb250cm9sbGVyKHZpZXdzLCB2aWV3LCBjYWNoZWRDb250cm9sbGVycywgY29udHJvbGxlcikge1xyXG5cdFx0dmFyIGNvbnRyb2xsZXJJbmRleCA9IG0ucmVkcmF3LnN0cmF0ZWd5KCkgPT09IFwiZGlmZlwiICYmIHZpZXdzID8gdmlld3MuaW5kZXhPZih2aWV3KSA6IC0xO1xyXG5cdFx0cmV0dXJuIGNvbnRyb2xsZXJJbmRleCA+IC0xID8gY2FjaGVkQ29udHJvbGxlcnNbY29udHJvbGxlckluZGV4XSA6XHJcblx0XHRcdHR5cGVvZiBjb250cm9sbGVyID09PSBcImZ1bmN0aW9uXCIgPyBuZXcgY29udHJvbGxlcigpIDoge307XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiB1cGRhdGVMaXN0cyh2aWV3cywgY29udHJvbGxlcnMsIHZpZXcsIGNvbnRyb2xsZXIpIHtcclxuXHRcdGlmIChjb250cm9sbGVyLm9udW5sb2FkICE9IG51bGwpIHVubG9hZGVycy5wdXNoKHtjb250cm9sbGVyOiBjb250cm9sbGVyLCBoYW5kbGVyOiBjb250cm9sbGVyLm9udW5sb2FkfSk7XHJcblx0XHR2aWV3cy5wdXNoKHZpZXcpO1xyXG5cdFx0Y29udHJvbGxlcnMucHVzaChjb250cm9sbGVyKTtcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGNoZWNrVmlldyhkYXRhLCB2aWV3LCBjYWNoZWQsIGNhY2hlZENvbnRyb2xsZXJzLCBjb250cm9sbGVycywgdmlld3MpIHtcclxuXHRcdHZhciBjb250cm9sbGVyID0gZ2V0Q29udHJvbGxlcihjYWNoZWQudmlld3MsIHZpZXcsIGNhY2hlZENvbnRyb2xsZXJzLCBkYXRhLmNvbnRyb2xsZXIpO1xyXG5cdFx0Ly9GYXN0ZXIgdG8gY29lcmNlIHRvIG51bWJlciBhbmQgY2hlY2sgZm9yIE5hTlxyXG5cdFx0dmFyIGtleSA9ICsoZGF0YSAmJiBkYXRhLmF0dHJzICYmIGRhdGEuYXR0cnMua2V5KTtcclxuXHRcdGRhdGEgPSBwZW5kaW5nUmVxdWVzdHMgPT09IDAgfHwgZm9yY2luZyB8fCBjYWNoZWRDb250cm9sbGVycyAmJiBjYWNoZWRDb250cm9sbGVycy5pbmRleE9mKGNvbnRyb2xsZXIpID4gLTEgPyBkYXRhLnZpZXcoY29udHJvbGxlcikgOiB7dGFnOiBcInBsYWNlaG9sZGVyXCJ9O1xyXG5cdFx0aWYgKGRhdGEuc3VidHJlZSA9PT0gXCJyZXRhaW5cIikgcmV0dXJuIGNhY2hlZDtcclxuXHRcdGlmIChrZXkgPT09IGtleSkgKGRhdGEuYXR0cnMgPSBkYXRhLmF0dHJzIHx8IHt9KS5rZXkgPSBrZXk7XHJcblx0XHR1cGRhdGVMaXN0cyh2aWV3cywgY29udHJvbGxlcnMsIHZpZXcsIGNvbnRyb2xsZXIpO1xyXG5cdFx0cmV0dXJuIGRhdGE7XHJcblx0fVxyXG5cclxuXHRmdW5jdGlvbiBtYXJrVmlld3MoZGF0YSwgY2FjaGVkLCB2aWV3cywgY29udHJvbGxlcnMpIHtcclxuXHRcdHZhciBjYWNoZWRDb250cm9sbGVycyA9IGNhY2hlZCAmJiBjYWNoZWQuY29udHJvbGxlcnM7XHJcblx0XHR3aGlsZSAoZGF0YS52aWV3ICE9IG51bGwpIGRhdGEgPSBjaGVja1ZpZXcoZGF0YSwgZGF0YS52aWV3LiRvcmlnaW5hbCB8fCBkYXRhLnZpZXcsIGNhY2hlZCwgY2FjaGVkQ29udHJvbGxlcnMsIGNvbnRyb2xsZXJzLCB2aWV3cyk7XHJcblx0XHRyZXR1cm4gZGF0YTtcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGJ1aWxkT2JqZWN0KGRhdGEsIGNhY2hlZCwgZWRpdGFibGUsIHBhcmVudEVsZW1lbnQsIGluZGV4LCBzaG91bGRSZWF0dGFjaCwgbmFtZXNwYWNlLCBjb25maWdzKSB7XHJcblx0XHR2YXIgdmlld3MgPSBbXSwgY29udHJvbGxlcnMgPSBbXTtcclxuXHRcdGRhdGEgPSBtYXJrVmlld3MoZGF0YSwgY2FjaGVkLCB2aWV3cywgY29udHJvbGxlcnMpO1xyXG5cdFx0aWYgKCFkYXRhLnRhZyAmJiBjb250cm9sbGVycy5sZW5ndGgpIHRocm93IG5ldyBFcnJvcihcIkNvbXBvbmVudCB0ZW1wbGF0ZSBtdXN0IHJldHVybiBhIHZpcnR1YWwgZWxlbWVudCwgbm90IGFuIGFycmF5LCBzdHJpbmcsIGV0Yy5cIik7XHJcblx0XHRkYXRhLmF0dHJzID0gZGF0YS5hdHRycyB8fCB7fTtcclxuXHRcdGNhY2hlZC5hdHRycyA9IGNhY2hlZC5hdHRycyB8fCB7fTtcclxuXHRcdHZhciBkYXRhQXR0cktleXMgPSBPYmplY3Qua2V5cyhkYXRhLmF0dHJzKTtcclxuXHRcdHZhciBoYXNLZXlzID0gZGF0YUF0dHJLZXlzLmxlbmd0aCA+IChcImtleVwiIGluIGRhdGEuYXR0cnMgPyAxIDogMCk7XHJcblx0XHRtYXliZVJlY3JlYXRlT2JqZWN0KGRhdGEsIGNhY2hlZCwgZGF0YUF0dHJLZXlzKTtcclxuXHRcdGlmICghaXNTdHJpbmcoZGF0YS50YWcpKSByZXR1cm47XHJcblx0XHR2YXIgaXNOZXcgPSBjYWNoZWQubm9kZXMubGVuZ3RoID09PSAwO1xyXG5cdFx0bmFtZXNwYWNlID0gZ2V0T2JqZWN0TmFtZXNwYWNlKGRhdGEsIG5hbWVzcGFjZSk7XHJcblx0XHR2YXIgbm9kZTtcclxuXHRcdGlmIChpc05ldykge1xyXG5cdFx0XHRub2RlID0gY29uc3RydWN0Tm9kZShkYXRhLCBuYW1lc3BhY2UpO1xyXG5cdFx0XHQvL3NldCBhdHRyaWJ1dGVzIGZpcnN0LCB0aGVuIGNyZWF0ZSBjaGlsZHJlblxyXG5cdFx0XHR2YXIgYXR0cnMgPSBjb25zdHJ1Y3RBdHRycyhkYXRhLCBub2RlLCBuYW1lc3BhY2UsIGhhc0tleXMpXHJcblx0XHRcdHZhciBjaGlsZHJlbiA9IGNvbnN0cnVjdENoaWxkcmVuKGRhdGEsIG5vZGUsIGNhY2hlZCwgZWRpdGFibGUsIG5hbWVzcGFjZSwgY29uZmlncyk7XHJcblx0XHRcdGNhY2hlZCA9IHJlY29uc3RydWN0Q2FjaGVkKGRhdGEsIGF0dHJzLCBjaGlsZHJlbiwgbm9kZSwgbmFtZXNwYWNlLCB2aWV3cywgY29udHJvbGxlcnMpO1xyXG5cdFx0fVxyXG5cdFx0ZWxzZSB7XHJcblx0XHRcdG5vZGUgPSBidWlsZFVwZGF0ZWROb2RlKGNhY2hlZCwgZGF0YSwgZWRpdGFibGUsIGhhc0tleXMsIG5hbWVzcGFjZSwgdmlld3MsIGNvbmZpZ3MsIGNvbnRyb2xsZXJzKTtcclxuXHRcdH1cclxuXHRcdGlmIChpc05ldyB8fCBzaG91bGRSZWF0dGFjaCA9PT0gdHJ1ZSAmJiBub2RlICE9IG51bGwpIGluc2VydE5vZGUocGFyZW50RWxlbWVudCwgbm9kZSwgaW5kZXgpO1xyXG5cdFx0Ly9zY2hlZHVsZSBjb25maWdzIHRvIGJlIGNhbGxlZC4gVGhleSBhcmUgY2FsbGVkIGFmdGVyIGBidWlsZGBcclxuXHRcdC8vZmluaXNoZXMgcnVubmluZ1xyXG5cdFx0c2NoZWR1bGVDb25maWdzVG9CZUNhbGxlZChjb25maWdzLCBkYXRhLCBub2RlLCBpc05ldywgY2FjaGVkKTtcclxuXHRcdHJldHVybiBjYWNoZWRcclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGJ1aWxkKHBhcmVudEVsZW1lbnQsIHBhcmVudFRhZywgcGFyZW50Q2FjaGUsIHBhcmVudEluZGV4LCBkYXRhLCBjYWNoZWQsIHNob3VsZFJlYXR0YWNoLCBpbmRleCwgZWRpdGFibGUsIG5hbWVzcGFjZSwgY29uZmlncykge1xyXG5cdFx0Ly9gYnVpbGRgIGlzIGEgcmVjdXJzaXZlIGZ1bmN0aW9uIHRoYXQgbWFuYWdlcyBjcmVhdGlvbi9kaWZmaW5nL3JlbW92YWxcclxuXHRcdC8vb2YgRE9NIGVsZW1lbnRzIGJhc2VkIG9uIGNvbXBhcmlzb24gYmV0d2VlbiBgZGF0YWAgYW5kIGBjYWNoZWRgXHJcblx0XHQvL3RoZSBkaWZmIGFsZ29yaXRobSBjYW4gYmUgc3VtbWFyaXplZCBhcyB0aGlzOlxyXG5cdFx0Ly8xIC0gY29tcGFyZSBgZGF0YWAgYW5kIGBjYWNoZWRgXHJcblx0XHQvLzIgLSBpZiB0aGV5IGFyZSBkaWZmZXJlbnQsIGNvcHkgYGRhdGFgIHRvIGBjYWNoZWRgIGFuZCB1cGRhdGUgdGhlIERPTVxyXG5cdFx0Ly8gICAgYmFzZWQgb24gd2hhdCB0aGUgZGlmZmVyZW5jZSBpc1xyXG5cdFx0Ly8zIC0gcmVjdXJzaXZlbHkgYXBwbHkgdGhpcyBhbGdvcml0aG0gZm9yIGV2ZXJ5IGFycmF5IGFuZCBmb3IgdGhlXHJcblx0XHQvLyAgICBjaGlsZHJlbiBvZiBldmVyeSB2aXJ0dWFsIGVsZW1lbnRcclxuXHJcblx0XHQvL3RoZSBgY2FjaGVkYCBkYXRhIHN0cnVjdHVyZSBpcyBlc3NlbnRpYWxseSB0aGUgc2FtZSBhcyB0aGUgcHJldmlvdXNcclxuXHRcdC8vcmVkcmF3J3MgYGRhdGFgIGRhdGEgc3RydWN0dXJlLCB3aXRoIGEgZmV3IGFkZGl0aW9uczpcclxuXHRcdC8vLSBgY2FjaGVkYCBhbHdheXMgaGFzIGEgcHJvcGVydHkgY2FsbGVkIGBub2Rlc2AsIHdoaWNoIGlzIGEgbGlzdCBvZlxyXG5cdFx0Ly8gICBET00gZWxlbWVudHMgdGhhdCBjb3JyZXNwb25kIHRvIHRoZSBkYXRhIHJlcHJlc2VudGVkIGJ5IHRoZVxyXG5cdFx0Ly8gICByZXNwZWN0aXZlIHZpcnR1YWwgZWxlbWVudFxyXG5cdFx0Ly8tIGluIG9yZGVyIHRvIHN1cHBvcnQgYXR0YWNoaW5nIGBub2Rlc2AgYXMgYSBwcm9wZXJ0eSBvZiBgY2FjaGVkYCxcclxuXHRcdC8vICAgYGNhY2hlZGAgaXMgKmFsd2F5cyogYSBub24tcHJpbWl0aXZlIG9iamVjdCwgaS5lLiBpZiB0aGUgZGF0YSB3YXNcclxuXHRcdC8vICAgYSBzdHJpbmcsIHRoZW4gY2FjaGVkIGlzIGEgU3RyaW5nIGluc3RhbmNlLiBJZiBkYXRhIHdhcyBgbnVsbGAgb3JcclxuXHRcdC8vICAgYHVuZGVmaW5lZGAsIGNhY2hlZCBpcyBgbmV3IFN0cmluZyhcIlwiKWBcclxuXHRcdC8vLSBgY2FjaGVkIGFsc28gaGFzIGEgYGNvbmZpZ0NvbnRleHRgIHByb3BlcnR5LCB3aGljaCBpcyB0aGUgc3RhdGVcclxuXHRcdC8vICAgc3RvcmFnZSBvYmplY3QgZXhwb3NlZCBieSBjb25maWcoZWxlbWVudCwgaXNJbml0aWFsaXplZCwgY29udGV4dClcclxuXHRcdC8vLSB3aGVuIGBjYWNoZWRgIGlzIGFuIE9iamVjdCwgaXQgcmVwcmVzZW50cyBhIHZpcnR1YWwgZWxlbWVudDsgd2hlblxyXG5cdFx0Ly8gICBpdCdzIGFuIEFycmF5LCBpdCByZXByZXNlbnRzIGEgbGlzdCBvZiBlbGVtZW50czsgd2hlbiBpdCdzIGFcclxuXHRcdC8vICAgU3RyaW5nLCBOdW1iZXIgb3IgQm9vbGVhbiwgaXQgcmVwcmVzZW50cyBhIHRleHQgbm9kZVxyXG5cclxuXHRcdC8vYHBhcmVudEVsZW1lbnRgIGlzIGEgRE9NIGVsZW1lbnQgdXNlZCBmb3IgVzNDIERPTSBBUEkgY2FsbHNcclxuXHRcdC8vYHBhcmVudFRhZ2AgaXMgb25seSB1c2VkIGZvciBoYW5kbGluZyBhIGNvcm5lciBjYXNlIGZvciB0ZXh0YXJlYVxyXG5cdFx0Ly92YWx1ZXNcclxuXHRcdC8vYHBhcmVudENhY2hlYCBpcyB1c2VkIHRvIHJlbW92ZSBub2RlcyBpbiBzb21lIG11bHRpLW5vZGUgY2FzZXNcclxuXHRcdC8vYHBhcmVudEluZGV4YCBhbmQgYGluZGV4YCBhcmUgdXNlZCB0byBmaWd1cmUgb3V0IHRoZSBvZmZzZXQgb2Ygbm9kZXMuXHJcblx0XHQvL1RoZXkncmUgYXJ0aWZhY3RzIGZyb20gYmVmb3JlIGFycmF5cyBzdGFydGVkIGJlaW5nIGZsYXR0ZW5lZCBhbmQgYXJlXHJcblx0XHQvL2xpa2VseSByZWZhY3RvcmFibGVcclxuXHRcdC8vYGRhdGFgIGFuZCBgY2FjaGVkYCBhcmUsIHJlc3BlY3RpdmVseSwgdGhlIG5ldyBhbmQgb2xkIG5vZGVzIGJlaW5nXHJcblx0XHQvL2RpZmZlZFxyXG5cdFx0Ly9gc2hvdWxkUmVhdHRhY2hgIGlzIGEgZmxhZyBpbmRpY2F0aW5nIHdoZXRoZXIgYSBwYXJlbnQgbm9kZSB3YXNcclxuXHRcdC8vcmVjcmVhdGVkIChpZiBzbywgYW5kIGlmIHRoaXMgbm9kZSBpcyByZXVzZWQsIHRoZW4gdGhpcyBub2RlIG11c3RcclxuXHRcdC8vcmVhdHRhY2ggaXRzZWxmIHRvIHRoZSBuZXcgcGFyZW50KVxyXG5cdFx0Ly9gZWRpdGFibGVgIGlzIGEgZmxhZyB0aGF0IGluZGljYXRlcyB3aGV0aGVyIGFuIGFuY2VzdG9yIGlzXHJcblx0XHQvL2NvbnRlbnRlZGl0YWJsZVxyXG5cdFx0Ly9gbmFtZXNwYWNlYCBpbmRpY2F0ZXMgdGhlIGNsb3Nlc3QgSFRNTCBuYW1lc3BhY2UgYXMgaXQgY2FzY2FkZXMgZG93blxyXG5cdFx0Ly9mcm9tIGFuIGFuY2VzdG9yXHJcblx0XHQvL2Bjb25maWdzYCBpcyBhIGxpc3Qgb2YgY29uZmlnIGZ1bmN0aW9ucyB0byBydW4gYWZ0ZXIgdGhlIHRvcG1vc3RcclxuXHRcdC8vYGJ1aWxkYCBjYWxsIGZpbmlzaGVzIHJ1bm5pbmdcclxuXHJcblx0XHQvL3RoZXJlJ3MgbG9naWMgdGhhdCByZWxpZXMgb24gdGhlIGFzc3VtcHRpb24gdGhhdCBudWxsIGFuZCB1bmRlZmluZWRcclxuXHRcdC8vZGF0YSBhcmUgZXF1aXZhbGVudCB0byBlbXB0eSBzdHJpbmdzXHJcblx0XHQvLy0gdGhpcyBwcmV2ZW50cyBsaWZlY3ljbGUgc3VycHJpc2VzIGZyb20gcHJvY2VkdXJhbCBoZWxwZXJzIHRoYXQgbWl4XHJcblx0XHQvLyAgaW1wbGljaXQgYW5kIGV4cGxpY2l0IHJldHVybiBzdGF0ZW1lbnRzIChlLmcuXHJcblx0XHQvLyAgZnVuY3Rpb24gZm9vKCkge2lmIChjb25kKSByZXR1cm4gbShcImRpdlwiKX1cclxuXHRcdC8vLSBpdCBzaW1wbGlmaWVzIGRpZmZpbmcgY29kZVxyXG5cdFx0ZGF0YSA9IGRhdGFUb1N0cmluZyhkYXRhKTtcclxuXHRcdGlmIChkYXRhLnN1YnRyZWUgPT09IFwicmV0YWluXCIpIHJldHVybiBjYWNoZWQ7XHJcblx0XHRjYWNoZWQgPSBtYWtlQ2FjaGUoZGF0YSwgY2FjaGVkLCBpbmRleCwgcGFyZW50SW5kZXgsIHBhcmVudENhY2hlKTtcclxuXHRcdHJldHVybiBpc0FycmF5KGRhdGEpID8gYnVpbGRBcnJheShkYXRhLCBjYWNoZWQsIHBhcmVudEVsZW1lbnQsIGluZGV4LCBwYXJlbnRUYWcsIHNob3VsZFJlYXR0YWNoLCBlZGl0YWJsZSwgbmFtZXNwYWNlLCBjb25maWdzKSA6XHJcblx0XHRcdGRhdGEgIT0gbnVsbCAmJiBpc09iamVjdChkYXRhKSA/IGJ1aWxkT2JqZWN0KGRhdGEsIGNhY2hlZCwgZWRpdGFibGUsIHBhcmVudEVsZW1lbnQsIGluZGV4LCBzaG91bGRSZWF0dGFjaCwgbmFtZXNwYWNlLCBjb25maWdzKSA6XHJcblx0XHRcdCFpc0Z1bmN0aW9uKGRhdGEpID8gaGFuZGxlVGV4dChjYWNoZWQsIGRhdGEsIGluZGV4LCBwYXJlbnRFbGVtZW50LCBzaG91bGRSZWF0dGFjaCwgZWRpdGFibGUsIHBhcmVudFRhZykgOlxyXG5cdFx0XHRjYWNoZWQ7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIHNvcnRDaGFuZ2VzKGEsIGIpIHsgcmV0dXJuIGEuYWN0aW9uIC0gYi5hY3Rpb24gfHwgYS5pbmRleCAtIGIuaW5kZXg7IH1cclxuXHRmdW5jdGlvbiBzZXRBdHRyaWJ1dGVzKG5vZGUsIHRhZywgZGF0YUF0dHJzLCBjYWNoZWRBdHRycywgbmFtZXNwYWNlKSB7XHJcblx0XHRmb3IgKHZhciBhdHRyTmFtZSBpbiBkYXRhQXR0cnMpIHtcclxuXHRcdFx0dmFyIGRhdGFBdHRyID0gZGF0YUF0dHJzW2F0dHJOYW1lXTtcclxuXHRcdFx0dmFyIGNhY2hlZEF0dHIgPSBjYWNoZWRBdHRyc1thdHRyTmFtZV07XHJcblx0XHRcdGlmICghKGF0dHJOYW1lIGluIGNhY2hlZEF0dHJzKSB8fCAoY2FjaGVkQXR0ciAhPT0gZGF0YUF0dHIpKSB7XHJcblx0XHRcdFx0Y2FjaGVkQXR0cnNbYXR0ck5hbWVdID0gZGF0YUF0dHI7XHJcblx0XHRcdFx0Ly9gY29uZmlnYCBpc24ndCBhIHJlYWwgYXR0cmlidXRlcywgc28gaWdub3JlIGl0XHJcblx0XHRcdFx0aWYgKGF0dHJOYW1lID09PSBcImNvbmZpZ1wiIHx8IGF0dHJOYW1lID09PSBcImtleVwiKSBjb250aW51ZTtcclxuXHRcdFx0XHQvL2hvb2sgZXZlbnQgaGFuZGxlcnMgdG8gdGhlIGF1dG8tcmVkcmF3aW5nIHN5c3RlbVxyXG5cdFx0XHRcdGVsc2UgaWYgKGlzRnVuY3Rpb24oZGF0YUF0dHIpICYmIGF0dHJOYW1lLnNsaWNlKDAsIDIpID09PSBcIm9uXCIpIHtcclxuXHRcdFx0XHRub2RlW2F0dHJOYW1lXSA9IGF1dG9yZWRyYXcoZGF0YUF0dHIsIG5vZGUpO1xyXG5cdFx0XHRcdH1cclxuXHRcdFx0XHQvL2hhbmRsZSBgc3R5bGU6IHsuLi59YFxyXG5cdFx0XHRcdGVsc2UgaWYgKGF0dHJOYW1lID09PSBcInN0eWxlXCIgJiYgZGF0YUF0dHIgIT0gbnVsbCAmJiBpc09iamVjdChkYXRhQXR0cikpIHtcclxuXHRcdFx0XHRmb3IgKHZhciBydWxlIGluIGRhdGFBdHRyKSB7XHJcblx0XHRcdFx0XHRcdGlmIChjYWNoZWRBdHRyID09IG51bGwgfHwgY2FjaGVkQXR0cltydWxlXSAhPT0gZGF0YUF0dHJbcnVsZV0pIG5vZGUuc3R5bGVbcnVsZV0gPSBkYXRhQXR0cltydWxlXTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdFx0Zm9yICh2YXIgcnVsZSBpbiBjYWNoZWRBdHRyKSB7XHJcblx0XHRcdFx0XHRcdGlmICghKHJ1bGUgaW4gZGF0YUF0dHIpKSBub2RlLnN0eWxlW3J1bGVdID0gXCJcIjtcclxuXHRcdFx0XHR9XHJcblx0XHRcdFx0fVxyXG5cdFx0XHRcdC8vaGFuZGxlIFNWR1xyXG5cdFx0XHRcdGVsc2UgaWYgKG5hbWVzcGFjZSAhPSBudWxsKSB7XHJcblx0XHRcdFx0aWYgKGF0dHJOYW1lID09PSBcImhyZWZcIikgbm9kZS5zZXRBdHRyaWJ1dGVOUyhcImh0dHA6Ly93d3cudzMub3JnLzE5OTkveGxpbmtcIiwgXCJocmVmXCIsIGRhdGFBdHRyKTtcclxuXHRcdFx0XHRlbHNlIG5vZGUuc2V0QXR0cmlidXRlKGF0dHJOYW1lID09PSBcImNsYXNzTmFtZVwiID8gXCJjbGFzc1wiIDogYXR0ck5hbWUsIGRhdGFBdHRyKTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdFx0Ly9oYW5kbGUgY2FzZXMgdGhhdCBhcmUgcHJvcGVydGllcyAoYnV0IGlnbm9yZSBjYXNlcyB3aGVyZSB3ZSBzaG91bGQgdXNlIHNldEF0dHJpYnV0ZSBpbnN0ZWFkKVxyXG5cdFx0XHRcdC8vLSBsaXN0IGFuZCBmb3JtIGFyZSB0eXBpY2FsbHkgdXNlZCBhcyBzdHJpbmdzLCBidXQgYXJlIERPTSBlbGVtZW50IHJlZmVyZW5jZXMgaW4ganNcclxuXHRcdFx0XHQvLy0gd2hlbiB1c2luZyBDU1Mgc2VsZWN0b3JzIChlLmcuIGBtKFwiW3N0eWxlPScnXVwiKWApLCBzdHlsZSBpcyB1c2VkIGFzIGEgc3RyaW5nLCBidXQgaXQncyBhbiBvYmplY3QgaW4ganNcclxuXHRcdFx0XHRlbHNlIGlmIChhdHRyTmFtZSBpbiBub2RlICYmIGF0dHJOYW1lICE9PSBcImxpc3RcIiAmJiBhdHRyTmFtZSAhPT0gXCJzdHlsZVwiICYmIGF0dHJOYW1lICE9PSBcImZvcm1cIiAmJiBhdHRyTmFtZSAhPT0gXCJ0eXBlXCIgJiYgYXR0ck5hbWUgIT09IFwid2lkdGhcIiAmJiBhdHRyTmFtZSAhPT0gXCJoZWlnaHRcIikge1xyXG5cdFx0XHRcdC8vIzM0OCBkb24ndCBzZXQgdGhlIHZhbHVlIGlmIG5vdCBuZWVkZWQgb3RoZXJ3aXNlIGN1cnNvciBwbGFjZW1lbnQgYnJlYWtzIGluIENocm9tZVxyXG5cdFx0XHRcdGlmICh0YWcgIT09IFwiaW5wdXRcIiB8fCBub2RlW2F0dHJOYW1lXSAhPT0gZGF0YUF0dHIpIG5vZGVbYXR0ck5hbWVdID0gZGF0YUF0dHI7XHJcblx0XHRcdFx0fVxyXG5cdFx0XHRcdGVsc2Ugbm9kZS5zZXRBdHRyaWJ1dGUoYXR0ck5hbWUsIGRhdGFBdHRyKTtcclxuXHRcdFx0fVxyXG5cdFx0XHQvLyMzNDggZGF0YUF0dHIgbWF5IG5vdCBiZSBhIHN0cmluZywgc28gdXNlIGxvb3NlIGNvbXBhcmlzb24gKGRvdWJsZSBlcXVhbCkgaW5zdGVhZCBvZiBzdHJpY3QgKHRyaXBsZSBlcXVhbClcclxuXHRcdFx0ZWxzZSBpZiAoYXR0ck5hbWUgPT09IFwidmFsdWVcIiAmJiB0YWcgPT09IFwiaW5wdXRcIiAmJiBub2RlLnZhbHVlICE9IGRhdGFBdHRyKSB7XHJcblx0XHRcdFx0bm9kZS52YWx1ZSA9IGRhdGFBdHRyO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblx0XHRyZXR1cm4gY2FjaGVkQXR0cnM7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIGNsZWFyKG5vZGVzLCBjYWNoZWQpIHtcclxuXHRcdGZvciAodmFyIGkgPSBub2Rlcy5sZW5ndGggLSAxOyBpID4gLTE7IGktLSkge1xyXG5cdFx0XHRpZiAobm9kZXNbaV0gJiYgbm9kZXNbaV0ucGFyZW50Tm9kZSkge1xyXG5cdFx0XHRcdHRyeSB7IG5vZGVzW2ldLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQobm9kZXNbaV0pOyB9XHJcblx0XHRcdFx0Y2F0Y2ggKGUpIHt9IC8vaWdub3JlIGlmIHRoaXMgZmFpbHMgZHVlIHRvIG9yZGVyIG9mIGV2ZW50cyAoc2VlIGh0dHA6Ly9zdGFja292ZXJmbG93LmNvbS9xdWVzdGlvbnMvMjE5MjYwODMvZmFpbGVkLXRvLWV4ZWN1dGUtcmVtb3ZlY2hpbGQtb24tbm9kZSlcclxuXHRcdFx0XHRjYWNoZWQgPSBbXS5jb25jYXQoY2FjaGVkKTtcclxuXHRcdFx0XHRpZiAoY2FjaGVkW2ldKSB1bmxvYWQoY2FjaGVkW2ldKTtcclxuXHRcdFx0fVxyXG5cdFx0fVxyXG5cdFx0Ly9yZWxlYXNlIG1lbW9yeSBpZiBub2RlcyBpcyBhbiBhcnJheS4gVGhpcyBjaGVjayBzaG91bGQgZmFpbCBpZiBub2RlcyBpcyBhIE5vZGVMaXN0IChzZWUgbG9vcCBhYm92ZSlcclxuXHRcdGlmIChub2Rlcy5sZW5ndGgpIG5vZGVzLmxlbmd0aCA9IDA7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIHVubG9hZChjYWNoZWQpIHtcclxuXHRcdGlmIChjYWNoZWQuY29uZmlnQ29udGV4dCAmJiBpc0Z1bmN0aW9uKGNhY2hlZC5jb25maWdDb250ZXh0Lm9udW5sb2FkKSkge1xyXG5cdFx0XHRjYWNoZWQuY29uZmlnQ29udGV4dC5vbnVubG9hZCgpO1xyXG5cdFx0XHRjYWNoZWQuY29uZmlnQ29udGV4dC5vbnVubG9hZCA9IG51bGw7XHJcblx0XHR9XHJcblx0XHRpZiAoY2FjaGVkLmNvbnRyb2xsZXJzKSB7XHJcblx0XHRcdGZvckVhY2goY2FjaGVkLmNvbnRyb2xsZXJzLCBmdW5jdGlvbiAoY29udHJvbGxlcikge1xyXG5cdFx0XHRcdGlmIChpc0Z1bmN0aW9uKGNvbnRyb2xsZXIub251bmxvYWQpKSBjb250cm9sbGVyLm9udW5sb2FkKHtwcmV2ZW50RGVmYXVsdDogbm9vcH0pO1xyXG5cdFx0XHR9KTtcclxuXHRcdH1cclxuXHRcdGlmIChjYWNoZWQuY2hpbGRyZW4pIHtcclxuXHRcdFx0aWYgKGlzQXJyYXkoY2FjaGVkLmNoaWxkcmVuKSkgZm9yRWFjaChjYWNoZWQuY2hpbGRyZW4sIHVubG9hZCk7XHJcblx0XHRcdGVsc2UgaWYgKGNhY2hlZC5jaGlsZHJlbi50YWcpIHVubG9hZChjYWNoZWQuY2hpbGRyZW4pO1xyXG5cdFx0fVxyXG5cdH1cclxuXHJcblx0dmFyIGluc2VydEFkamFjZW50QmVmb3JlRW5kID0gKGZ1bmN0aW9uICgpIHtcclxuXHRcdHZhciByYW5nZVN0cmF0ZWd5ID0gZnVuY3Rpb24gKHBhcmVudEVsZW1lbnQsIGRhdGEpIHtcclxuXHRcdFx0cGFyZW50RWxlbWVudC5hcHBlbmRDaGlsZCgkZG9jdW1lbnQuY3JlYXRlUmFuZ2UoKS5jcmVhdGVDb250ZXh0dWFsRnJhZ21lbnQoZGF0YSkpO1xyXG5cdFx0fTtcclxuXHRcdHZhciBpbnNlcnRBZGphY2VudFN0cmF0ZWd5ID0gZnVuY3Rpb24gKHBhcmVudEVsZW1lbnQsIGRhdGEpIHtcclxuXHRcdFx0cGFyZW50RWxlbWVudC5pbnNlcnRBZGphY2VudEhUTUwoXCJiZWZvcmVlbmRcIiwgZGF0YSk7XHJcblx0XHR9O1xyXG5cclxuXHRcdHRyeSB7XHJcblx0XHRcdCRkb2N1bWVudC5jcmVhdGVSYW5nZSgpLmNyZWF0ZUNvbnRleHR1YWxGcmFnbWVudCgneCcpO1xyXG5cdFx0XHRyZXR1cm4gcmFuZ2VTdHJhdGVneTtcclxuXHRcdH0gY2F0Y2ggKGUpIHtcclxuXHRcdFx0cmV0dXJuIGluc2VydEFkamFjZW50U3RyYXRlZ3k7XHJcblx0XHR9XHJcblx0fSkoKTtcclxuXHJcblx0ZnVuY3Rpb24gaW5qZWN0SFRNTChwYXJlbnRFbGVtZW50LCBpbmRleCwgZGF0YSkge1xyXG5cdFx0dmFyIG5leHRTaWJsaW5nID0gcGFyZW50RWxlbWVudC5jaGlsZE5vZGVzW2luZGV4XTtcclxuXHRcdGlmIChuZXh0U2libGluZykge1xyXG5cdFx0XHR2YXIgaXNFbGVtZW50ID0gbmV4dFNpYmxpbmcubm9kZVR5cGUgIT09IDE7XHJcblx0XHRcdHZhciBwbGFjZWhvbGRlciA9ICRkb2N1bWVudC5jcmVhdGVFbGVtZW50KFwic3BhblwiKTtcclxuXHRcdFx0aWYgKGlzRWxlbWVudCkge1xyXG5cdFx0XHRcdHBhcmVudEVsZW1lbnQuaW5zZXJ0QmVmb3JlKHBsYWNlaG9sZGVyLCBuZXh0U2libGluZyB8fCBudWxsKTtcclxuXHRcdFx0XHRwbGFjZWhvbGRlci5pbnNlcnRBZGphY2VudEhUTUwoXCJiZWZvcmViZWdpblwiLCBkYXRhKTtcclxuXHRcdFx0XHRwYXJlbnRFbGVtZW50LnJlbW92ZUNoaWxkKHBsYWNlaG9sZGVyKTtcclxuXHRcdFx0fVxyXG5cdFx0XHRlbHNlIG5leHRTaWJsaW5nLmluc2VydEFkamFjZW50SFRNTChcImJlZm9yZWJlZ2luXCIsIGRhdGEpO1xyXG5cdFx0fVxyXG5cdFx0ZWxzZSBpbnNlcnRBZGphY2VudEJlZm9yZUVuZChwYXJlbnRFbGVtZW50LCBkYXRhKTtcclxuXHJcblx0XHR2YXIgbm9kZXMgPSBbXTtcclxuXHRcdHdoaWxlIChwYXJlbnRFbGVtZW50LmNoaWxkTm9kZXNbaW5kZXhdICE9PSBuZXh0U2libGluZykge1xyXG5cdFx0XHRub2Rlcy5wdXNoKHBhcmVudEVsZW1lbnQuY2hpbGROb2Rlc1tpbmRleF0pO1xyXG5cdFx0XHRpbmRleCsrO1xyXG5cdFx0fVxyXG5cdFx0cmV0dXJuIG5vZGVzO1xyXG5cdH1cclxuXHRmdW5jdGlvbiBhdXRvcmVkcmF3KGNhbGxiYWNrLCBvYmplY3QpIHtcclxuXHRcdHJldHVybiBmdW5jdGlvbihlKSB7XHJcblx0XHRcdGUgPSBlIHx8IGV2ZW50O1xyXG5cdFx0XHRtLnJlZHJhdy5zdHJhdGVneShcImRpZmZcIik7XHJcblx0XHRcdG0uc3RhcnRDb21wdXRhdGlvbigpO1xyXG5cdFx0XHR0cnkgeyByZXR1cm4gY2FsbGJhY2suY2FsbChvYmplY3QsIGUpOyB9XHJcblx0XHRcdGZpbmFsbHkge1xyXG5cdFx0XHRcdGVuZEZpcnN0Q29tcHV0YXRpb24oKTtcclxuXHRcdFx0fVxyXG5cdFx0fTtcclxuXHR9XHJcblxyXG5cdHZhciBodG1sO1xyXG5cdHZhciBkb2N1bWVudE5vZGUgPSB7XHJcblx0XHRhcHBlbmRDaGlsZDogZnVuY3Rpb24obm9kZSkge1xyXG5cdFx0XHRpZiAoaHRtbCA9PT0gdW5kZWZpbmVkKSBodG1sID0gJGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoXCJodG1sXCIpO1xyXG5cdFx0XHRpZiAoJGRvY3VtZW50LmRvY3VtZW50RWxlbWVudCAmJiAkZG9jdW1lbnQuZG9jdW1lbnRFbGVtZW50ICE9PSBub2RlKSB7XHJcblx0XHRcdFx0JGRvY3VtZW50LnJlcGxhY2VDaGlsZChub2RlLCAkZG9jdW1lbnQuZG9jdW1lbnRFbGVtZW50KTtcclxuXHRcdFx0fVxyXG5cdFx0XHRlbHNlICRkb2N1bWVudC5hcHBlbmRDaGlsZChub2RlKTtcclxuXHRcdFx0dGhpcy5jaGlsZE5vZGVzID0gJGRvY3VtZW50LmNoaWxkTm9kZXM7XHJcblx0XHR9LFxyXG5cdFx0aW5zZXJ0QmVmb3JlOiBmdW5jdGlvbihub2RlKSB7XHJcblx0XHRcdHRoaXMuYXBwZW5kQ2hpbGQobm9kZSk7XHJcblx0XHR9LFxyXG5cdFx0Y2hpbGROb2RlczogW11cclxuXHR9O1xyXG5cdHZhciBub2RlQ2FjaGUgPSBbXSwgY2VsbENhY2hlID0ge307XHJcblx0bS5yZW5kZXIgPSBmdW5jdGlvbihyb290LCBjZWxsLCBmb3JjZVJlY3JlYXRpb24pIHtcclxuXHRcdHZhciBjb25maWdzID0gW107XHJcblx0XHRpZiAoIXJvb3QpIHRocm93IG5ldyBFcnJvcihcIkVuc3VyZSB0aGUgRE9NIGVsZW1lbnQgYmVpbmcgcGFzc2VkIHRvIG0ucm91dGUvbS5tb3VudC9tLnJlbmRlciBpcyBub3QgdW5kZWZpbmVkLlwiKTtcclxuXHRcdHZhciBpZCA9IGdldENlbGxDYWNoZUtleShyb290KTtcclxuXHRcdHZhciBpc0RvY3VtZW50Um9vdCA9IHJvb3QgPT09ICRkb2N1bWVudDtcclxuXHRcdHZhciBub2RlID0gaXNEb2N1bWVudFJvb3QgfHwgcm9vdCA9PT0gJGRvY3VtZW50LmRvY3VtZW50RWxlbWVudCA/IGRvY3VtZW50Tm9kZSA6IHJvb3Q7XHJcblx0XHRpZiAoaXNEb2N1bWVudFJvb3QgJiYgY2VsbC50YWcgIT09IFwiaHRtbFwiKSBjZWxsID0ge3RhZzogXCJodG1sXCIsIGF0dHJzOiB7fSwgY2hpbGRyZW46IGNlbGx9O1xyXG5cdFx0aWYgKGNlbGxDYWNoZVtpZF0gPT09IHVuZGVmaW5lZCkgY2xlYXIobm9kZS5jaGlsZE5vZGVzKTtcclxuXHRcdGlmIChmb3JjZVJlY3JlYXRpb24gPT09IHRydWUpIHJlc2V0KHJvb3QpO1xyXG5cdFx0Y2VsbENhY2hlW2lkXSA9IGJ1aWxkKG5vZGUsIG51bGwsIHVuZGVmaW5lZCwgdW5kZWZpbmVkLCBjZWxsLCBjZWxsQ2FjaGVbaWRdLCBmYWxzZSwgMCwgbnVsbCwgdW5kZWZpbmVkLCBjb25maWdzKTtcclxuXHRcdGZvckVhY2goY29uZmlncywgZnVuY3Rpb24gKGNvbmZpZykgeyBjb25maWcoKTsgfSk7XHJcblx0fTtcclxuXHRmdW5jdGlvbiBnZXRDZWxsQ2FjaGVLZXkoZWxlbWVudCkge1xyXG5cdFx0dmFyIGluZGV4ID0gbm9kZUNhY2hlLmluZGV4T2YoZWxlbWVudCk7XHJcblx0XHRyZXR1cm4gaW5kZXggPCAwID8gbm9kZUNhY2hlLnB1c2goZWxlbWVudCkgLSAxIDogaW5kZXg7XHJcblx0fVxyXG5cclxuXHRtLnRydXN0ID0gZnVuY3Rpb24odmFsdWUpIHtcclxuXHRcdHZhbHVlID0gbmV3IFN0cmluZyh2YWx1ZSk7XHJcblx0XHR2YWx1ZS4kdHJ1c3RlZCA9IHRydWU7XHJcblx0XHRyZXR1cm4gdmFsdWU7XHJcblx0fTtcclxuXHJcblx0ZnVuY3Rpb24gZ2V0dGVyc2V0dGVyKHN0b3JlKSB7XHJcblx0XHR2YXIgcHJvcCA9IGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRpZiAoYXJndW1lbnRzLmxlbmd0aCkgc3RvcmUgPSBhcmd1bWVudHNbMF07XHJcblx0XHRcdHJldHVybiBzdG9yZTtcclxuXHRcdH07XHJcblxyXG5cdFx0cHJvcC50b0pTT04gPSBmdW5jdGlvbigpIHtcclxuXHRcdFx0cmV0dXJuIHN0b3JlO1xyXG5cdFx0fTtcclxuXHJcblx0XHRyZXR1cm4gcHJvcDtcclxuXHR9XHJcblxyXG5cdG0ucHJvcCA9IGZ1bmN0aW9uIChzdG9yZSkge1xyXG5cdFx0Ly9ub3RlOiB1c2luZyBub24tc3RyaWN0IGVxdWFsaXR5IGNoZWNrIGhlcmUgYmVjYXVzZSB3ZSdyZSBjaGVja2luZyBpZiBzdG9yZSBpcyBudWxsIE9SIHVuZGVmaW5lZFxyXG5cdFx0aWYgKChzdG9yZSAhPSBudWxsICYmIGlzT2JqZWN0KHN0b3JlKSB8fCBpc0Z1bmN0aW9uKHN0b3JlKSkgJiYgaXNGdW5jdGlvbihzdG9yZS50aGVuKSkge1xyXG5cdFx0XHRyZXR1cm4gcHJvcGlmeShzdG9yZSk7XHJcblx0XHR9XHJcblxyXG5cdFx0cmV0dXJuIGdldHRlcnNldHRlcihzdG9yZSk7XHJcblx0fTtcclxuXHJcblx0dmFyIHJvb3RzID0gW10sIGNvbXBvbmVudHMgPSBbXSwgY29udHJvbGxlcnMgPSBbXSwgbGFzdFJlZHJhd0lkID0gbnVsbCwgbGFzdFJlZHJhd0NhbGxUaW1lID0gMCwgY29tcHV0ZVByZVJlZHJhd0hvb2sgPSBudWxsLCBjb21wdXRlUG9zdFJlZHJhd0hvb2sgPSBudWxsLCB0b3BDb21wb25lbnQsIHVubG9hZGVycyA9IFtdO1xyXG5cdHZhciBGUkFNRV9CVURHRVQgPSAxNjsgLy82MCBmcmFtZXMgcGVyIHNlY29uZCA9IDEgY2FsbCBwZXIgMTYgbXNcclxuXHRmdW5jdGlvbiBwYXJhbWV0ZXJpemUoY29tcG9uZW50LCBhcmdzKSB7XHJcblx0XHR2YXIgY29udHJvbGxlciA9IGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRyZXR1cm4gKGNvbXBvbmVudC5jb250cm9sbGVyIHx8IG5vb3ApLmFwcGx5KHRoaXMsIGFyZ3MpIHx8IHRoaXM7XHJcblx0XHR9O1xyXG5cdFx0aWYgKGNvbXBvbmVudC5jb250cm9sbGVyKSBjb250cm9sbGVyLnByb3RvdHlwZSA9IGNvbXBvbmVudC5jb250cm9sbGVyLnByb3RvdHlwZTtcclxuXHRcdHZhciB2aWV3ID0gZnVuY3Rpb24oY3RybCkge1xyXG5cdFx0XHR2YXIgY3VycmVudEFyZ3MgPSBhcmd1bWVudHMubGVuZ3RoID4gMSA/IGFyZ3MuY29uY2F0KFtdLnNsaWNlLmNhbGwoYXJndW1lbnRzLCAxKSkgOiBhcmdzO1xyXG5cdFx0XHRyZXR1cm4gY29tcG9uZW50LnZpZXcuYXBwbHkoY29tcG9uZW50LCBjdXJyZW50QXJncyA/IFtjdHJsXS5jb25jYXQoY3VycmVudEFyZ3MpIDogW2N0cmxdKTtcclxuXHRcdH07XHJcblx0XHR2aWV3LiRvcmlnaW5hbCA9IGNvbXBvbmVudC52aWV3O1xyXG5cdFx0dmFyIG91dHB1dCA9IHtjb250cm9sbGVyOiBjb250cm9sbGVyLCB2aWV3OiB2aWV3fTtcclxuXHRcdGlmIChhcmdzWzBdICYmIGFyZ3NbMF0ua2V5ICE9IG51bGwpIG91dHB1dC5hdHRycyA9IHtrZXk6IGFyZ3NbMF0ua2V5fTtcclxuXHRcdHJldHVybiBvdXRwdXQ7XHJcblx0fVxyXG5cdG0uY29tcG9uZW50ID0gZnVuY3Rpb24oY29tcG9uZW50KSB7XHJcblx0XHRmb3IgKHZhciBhcmdzID0gW10sIGkgPSAxOyBpIDwgYXJndW1lbnRzLmxlbmd0aDsgaSsrKSBhcmdzLnB1c2goYXJndW1lbnRzW2ldKTtcclxuXHRcdHJldHVybiBwYXJhbWV0ZXJpemUoY29tcG9uZW50LCBhcmdzKTtcclxuXHR9O1xyXG5cdG0ubW91bnQgPSBtLm1vZHVsZSA9IGZ1bmN0aW9uKHJvb3QsIGNvbXBvbmVudCkge1xyXG5cdFx0aWYgKCFyb290KSB0aHJvdyBuZXcgRXJyb3IoXCJQbGVhc2UgZW5zdXJlIHRoZSBET00gZWxlbWVudCBleGlzdHMgYmVmb3JlIHJlbmRlcmluZyBhIHRlbXBsYXRlIGludG8gaXQuXCIpO1xyXG5cdFx0dmFyIGluZGV4ID0gcm9vdHMuaW5kZXhPZihyb290KTtcclxuXHRcdGlmIChpbmRleCA8IDApIGluZGV4ID0gcm9vdHMubGVuZ3RoO1xyXG5cclxuXHRcdHZhciBpc1ByZXZlbnRlZCA9IGZhbHNlO1xyXG5cdFx0dmFyIGV2ZW50ID0ge3ByZXZlbnREZWZhdWx0OiBmdW5jdGlvbigpIHtcclxuXHRcdFx0aXNQcmV2ZW50ZWQgPSB0cnVlO1xyXG5cdFx0XHRjb21wdXRlUHJlUmVkcmF3SG9vayA9IGNvbXB1dGVQb3N0UmVkcmF3SG9vayA9IG51bGw7XHJcblx0XHR9fTtcclxuXHJcblx0XHRmb3JFYWNoKHVubG9hZGVycywgZnVuY3Rpb24gKHVubG9hZGVyKSB7XHJcblx0XHRcdHVubG9hZGVyLmhhbmRsZXIuY2FsbCh1bmxvYWRlci5jb250cm9sbGVyLCBldmVudCk7XHJcblx0XHRcdHVubG9hZGVyLmNvbnRyb2xsZXIub251bmxvYWQgPSBudWxsO1xyXG5cdFx0fSk7XHJcblxyXG5cdFx0aWYgKGlzUHJldmVudGVkKSB7XHJcblx0XHRcdGZvckVhY2godW5sb2FkZXJzLCBmdW5jdGlvbiAodW5sb2FkZXIpIHtcclxuXHRcdFx0XHR1bmxvYWRlci5jb250cm9sbGVyLm9udW5sb2FkID0gdW5sb2FkZXIuaGFuZGxlcjtcclxuXHRcdFx0fSk7XHJcblx0XHR9XHJcblx0XHRlbHNlIHVubG9hZGVycyA9IFtdO1xyXG5cclxuXHRcdGlmIChjb250cm9sbGVyc1tpbmRleF0gJiYgaXNGdW5jdGlvbihjb250cm9sbGVyc1tpbmRleF0ub251bmxvYWQpKSB7XHJcblx0XHRcdGNvbnRyb2xsZXJzW2luZGV4XS5vbnVubG9hZChldmVudCk7XHJcblx0XHR9XHJcblxyXG5cdFx0dmFyIGlzTnVsbENvbXBvbmVudCA9IGNvbXBvbmVudCA9PT0gbnVsbDtcclxuXHJcblx0XHRpZiAoIWlzUHJldmVudGVkKSB7XHJcblx0XHRcdG0ucmVkcmF3LnN0cmF0ZWd5KFwiYWxsXCIpO1xyXG5cdFx0XHRtLnN0YXJ0Q29tcHV0YXRpb24oKTtcclxuXHRcdFx0cm9vdHNbaW5kZXhdID0gcm9vdDtcclxuXHRcdFx0dmFyIGN1cnJlbnRDb21wb25lbnQgPSBjb21wb25lbnQgPyAodG9wQ29tcG9uZW50ID0gY29tcG9uZW50KSA6ICh0b3BDb21wb25lbnQgPSBjb21wb25lbnQgPSB7Y29udHJvbGxlcjogbm9vcH0pO1xyXG5cdFx0XHR2YXIgY29udHJvbGxlciA9IG5ldyAoY29tcG9uZW50LmNvbnRyb2xsZXIgfHwgbm9vcCkoKTtcclxuXHRcdFx0Ly9jb250cm9sbGVycyBtYXkgY2FsbCBtLm1vdW50IHJlY3Vyc2l2ZWx5ICh2aWEgbS5yb3V0ZSByZWRpcmVjdHMsIGZvciBleGFtcGxlKVxyXG5cdFx0XHQvL3RoaXMgY29uZGl0aW9uYWwgZW5zdXJlcyBvbmx5IHRoZSBsYXN0IHJlY3Vyc2l2ZSBtLm1vdW50IGNhbGwgaXMgYXBwbGllZFxyXG5cdFx0XHRpZiAoY3VycmVudENvbXBvbmVudCA9PT0gdG9wQ29tcG9uZW50KSB7XHJcblx0XHRcdFx0Y29udHJvbGxlcnNbaW5kZXhdID0gY29udHJvbGxlcjtcclxuXHRcdFx0XHRjb21wb25lbnRzW2luZGV4XSA9IGNvbXBvbmVudDtcclxuXHRcdFx0fVxyXG5cdFx0XHRlbmRGaXJzdENvbXB1dGF0aW9uKCk7XHJcblx0XHRcdGlmIChpc051bGxDb21wb25lbnQpIHtcclxuXHRcdFx0XHRyZW1vdmVSb290RWxlbWVudChyb290LCBpbmRleCk7XHJcblx0XHRcdH1cclxuXHRcdFx0cmV0dXJuIGNvbnRyb2xsZXJzW2luZGV4XTtcclxuXHRcdH1cclxuXHRcdGlmIChpc051bGxDb21wb25lbnQpIHtcclxuXHRcdFx0cmVtb3ZlUm9vdEVsZW1lbnQocm9vdCwgaW5kZXgpO1xyXG5cdFx0fVxyXG5cdH07XHJcblxyXG5cdGZ1bmN0aW9uIHJlbW92ZVJvb3RFbGVtZW50KHJvb3QsIGluZGV4KSB7XHJcblx0XHRyb290cy5zcGxpY2UoaW5kZXgsIDEpO1xyXG5cdFx0Y29udHJvbGxlcnMuc3BsaWNlKGluZGV4LCAxKTtcclxuXHRcdGNvbXBvbmVudHMuc3BsaWNlKGluZGV4LCAxKTtcclxuXHRcdHJlc2V0KHJvb3QpO1xyXG5cdFx0bm9kZUNhY2hlLnNwbGljZShnZXRDZWxsQ2FjaGVLZXkocm9vdCksIDEpO1xyXG5cdH1cclxuXHJcblx0dmFyIHJlZHJhd2luZyA9IGZhbHNlLCBmb3JjaW5nID0gZmFsc2U7XHJcblx0bS5yZWRyYXcgPSBmdW5jdGlvbihmb3JjZSkge1xyXG5cdFx0aWYgKHJlZHJhd2luZykgcmV0dXJuO1xyXG5cdFx0cmVkcmF3aW5nID0gdHJ1ZTtcclxuXHRcdGlmIChmb3JjZSkgZm9yY2luZyA9IHRydWU7XHJcblx0XHR0cnkge1xyXG5cdFx0XHQvL2xhc3RSZWRyYXdJZCBpcyBhIHBvc2l0aXZlIG51bWJlciBpZiBhIHNlY29uZCByZWRyYXcgaXMgcmVxdWVzdGVkIGJlZm9yZSB0aGUgbmV4dCBhbmltYXRpb24gZnJhbWVcclxuXHRcdFx0Ly9sYXN0UmVkcmF3SUQgaXMgbnVsbCBpZiBpdCdzIHRoZSBmaXJzdCByZWRyYXcgYW5kIG5vdCBhbiBldmVudCBoYW5kbGVyXHJcblx0XHRcdGlmIChsYXN0UmVkcmF3SWQgJiYgIWZvcmNlKSB7XHJcblx0XHRcdFx0Ly93aGVuIHNldFRpbWVvdXQ6IG9ubHkgcmVzY2hlZHVsZSByZWRyYXcgaWYgdGltZSBiZXR3ZWVuIG5vdyBhbmQgcHJldmlvdXMgcmVkcmF3IGlzIGJpZ2dlciB0aGFuIGEgZnJhbWUsIG90aGVyd2lzZSBrZWVwIGN1cnJlbnRseSBzY2hlZHVsZWQgdGltZW91dFxyXG5cdFx0XHRcdC8vd2hlbiByQUY6IGFsd2F5cyByZXNjaGVkdWxlIHJlZHJhd1xyXG5cdFx0XHRcdGlmICgkcmVxdWVzdEFuaW1hdGlvbkZyYW1lID09PSB3aW5kb3cucmVxdWVzdEFuaW1hdGlvbkZyYW1lIHx8IG5ldyBEYXRlIC0gbGFzdFJlZHJhd0NhbGxUaW1lID4gRlJBTUVfQlVER0VUKSB7XHJcblx0XHRcdFx0XHRpZiAobGFzdFJlZHJhd0lkID4gMCkgJGNhbmNlbEFuaW1hdGlvbkZyYW1lKGxhc3RSZWRyYXdJZCk7XHJcblx0XHRcdFx0XHRsYXN0UmVkcmF3SWQgPSAkcmVxdWVzdEFuaW1hdGlvbkZyYW1lKHJlZHJhdywgRlJBTUVfQlVER0VUKTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdH1cclxuXHRcdFx0ZWxzZSB7XHJcblx0XHRcdFx0cmVkcmF3KCk7XHJcblx0XHRcdFx0bGFzdFJlZHJhd0lkID0gJHJlcXVlc3RBbmltYXRpb25GcmFtZShmdW5jdGlvbigpIHsgbGFzdFJlZHJhd0lkID0gbnVsbDsgfSwgRlJBTUVfQlVER0VUKTtcclxuXHRcdFx0fVxyXG5cdFx0fVxyXG5cdFx0ZmluYWxseSB7XHJcblx0XHRcdHJlZHJhd2luZyA9IGZvcmNpbmcgPSBmYWxzZTtcclxuXHRcdH1cclxuXHR9O1xyXG5cdG0ucmVkcmF3LnN0cmF0ZWd5ID0gbS5wcm9wKCk7XHJcblx0ZnVuY3Rpb24gcmVkcmF3KCkge1xyXG5cdFx0aWYgKGNvbXB1dGVQcmVSZWRyYXdIb29rKSB7XHJcblx0XHRcdGNvbXB1dGVQcmVSZWRyYXdIb29rKCk7XHJcblx0XHRcdGNvbXB1dGVQcmVSZWRyYXdIb29rID0gbnVsbDtcclxuXHRcdH1cclxuXHRcdGZvckVhY2gocm9vdHMsIGZ1bmN0aW9uIChyb290LCBpKSB7XHJcblx0XHRcdHZhciBjb21wb25lbnQgPSBjb21wb25lbnRzW2ldO1xyXG5cdFx0XHRpZiAoY29udHJvbGxlcnNbaV0pIHtcclxuXHRcdFx0XHR2YXIgYXJncyA9IFtjb250cm9sbGVyc1tpXV07XHJcblx0XHRcdFx0bS5yZW5kZXIocm9vdCwgY29tcG9uZW50LnZpZXcgPyBjb21wb25lbnQudmlldyhjb250cm9sbGVyc1tpXSwgYXJncykgOiBcIlwiKTtcclxuXHRcdFx0fVxyXG5cdFx0fSk7XHJcblx0XHQvL2FmdGVyIHJlbmRlcmluZyB3aXRoaW4gYSByb3V0ZWQgY29udGV4dCwgd2UgbmVlZCB0byBzY3JvbGwgYmFjayB0byB0aGUgdG9wLCBhbmQgZmV0Y2ggdGhlIGRvY3VtZW50IHRpdGxlIGZvciBoaXN0b3J5LnB1c2hTdGF0ZVxyXG5cdFx0aWYgKGNvbXB1dGVQb3N0UmVkcmF3SG9vaykge1xyXG5cdFx0XHRjb21wdXRlUG9zdFJlZHJhd0hvb2soKTtcclxuXHRcdFx0Y29tcHV0ZVBvc3RSZWRyYXdIb29rID0gbnVsbDtcclxuXHRcdH1cclxuXHRcdGxhc3RSZWRyYXdJZCA9IG51bGw7XHJcblx0XHRsYXN0UmVkcmF3Q2FsbFRpbWUgPSBuZXcgRGF0ZTtcclxuXHRcdG0ucmVkcmF3LnN0cmF0ZWd5KFwiZGlmZlwiKTtcclxuXHR9XHJcblxyXG5cdHZhciBwZW5kaW5nUmVxdWVzdHMgPSAwO1xyXG5cdG0uc3RhcnRDb21wdXRhdGlvbiA9IGZ1bmN0aW9uKCkgeyBwZW5kaW5nUmVxdWVzdHMrKzsgfTtcclxuXHRtLmVuZENvbXB1dGF0aW9uID0gZnVuY3Rpb24oKSB7XHJcblx0XHRpZiAocGVuZGluZ1JlcXVlc3RzID4gMSkgcGVuZGluZ1JlcXVlc3RzLS07XHJcblx0XHRlbHNlIHtcclxuXHRcdFx0cGVuZGluZ1JlcXVlc3RzID0gMDtcclxuXHRcdFx0bS5yZWRyYXcoKTtcclxuXHRcdH1cclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGVuZEZpcnN0Q29tcHV0YXRpb24oKSB7XHJcblx0XHRpZiAobS5yZWRyYXcuc3RyYXRlZ3koKSA9PT0gXCJub25lXCIpIHtcclxuXHRcdFx0cGVuZGluZ1JlcXVlc3RzLS07XHJcblx0XHRcdG0ucmVkcmF3LnN0cmF0ZWd5KFwiZGlmZlwiKTtcclxuXHRcdH1cclxuXHRcdGVsc2UgbS5lbmRDb21wdXRhdGlvbigpO1xyXG5cdH1cclxuXHJcblx0bS53aXRoQXR0ciA9IGZ1bmN0aW9uKHByb3AsIHdpdGhBdHRyQ2FsbGJhY2ssIGNhbGxiYWNrVGhpcykge1xyXG5cdFx0cmV0dXJuIGZ1bmN0aW9uKGUpIHtcclxuXHRcdFx0ZSA9IGUgfHwgZXZlbnQ7XHJcblx0XHRcdHZhciBjdXJyZW50VGFyZ2V0ID0gZS5jdXJyZW50VGFyZ2V0IHx8IHRoaXM7XHJcblx0XHRcdHZhciBfdGhpcyA9IGNhbGxiYWNrVGhpcyB8fCB0aGlzO1xyXG5cdFx0XHR3aXRoQXR0ckNhbGxiYWNrLmNhbGwoX3RoaXMsIHByb3AgaW4gY3VycmVudFRhcmdldCA/IGN1cnJlbnRUYXJnZXRbcHJvcF0gOiBjdXJyZW50VGFyZ2V0LmdldEF0dHJpYnV0ZShwcm9wKSk7XHJcblx0XHR9O1xyXG5cdH07XHJcblxyXG5cdC8vcm91dGluZ1xyXG5cdHZhciBtb2RlcyA9IHtwYXRobmFtZTogXCJcIiwgaGFzaDogXCIjXCIsIHNlYXJjaDogXCI/XCJ9O1xyXG5cdHZhciByZWRpcmVjdCA9IG5vb3AsIHJvdXRlUGFyYW1zLCBjdXJyZW50Um91dGUsIGlzRGVmYXVsdFJvdXRlID0gZmFsc2U7XHJcblx0bS5yb3V0ZSA9IGZ1bmN0aW9uKHJvb3QsIGFyZzEsIGFyZzIsIHZkb20pIHtcclxuXHRcdC8vbS5yb3V0ZSgpXHJcblx0XHRpZiAoYXJndW1lbnRzLmxlbmd0aCA9PT0gMCkgcmV0dXJuIGN1cnJlbnRSb3V0ZTtcclxuXHRcdC8vbS5yb3V0ZShlbCwgZGVmYXVsdFJvdXRlLCByb3V0ZXMpXHJcblx0XHRlbHNlIGlmIChhcmd1bWVudHMubGVuZ3RoID09PSAzICYmIGlzU3RyaW5nKGFyZzEpKSB7XHJcblx0XHRcdHJlZGlyZWN0ID0gZnVuY3Rpb24oc291cmNlKSB7XHJcblx0XHRcdFx0dmFyIHBhdGggPSBjdXJyZW50Um91dGUgPSBub3JtYWxpemVSb3V0ZShzb3VyY2UpO1xyXG5cdFx0XHRcdGlmICghcm91dGVCeVZhbHVlKHJvb3QsIGFyZzIsIHBhdGgpKSB7XHJcblx0XHRcdFx0XHRpZiAoaXNEZWZhdWx0Um91dGUpIHRocm93IG5ldyBFcnJvcihcIkVuc3VyZSB0aGUgZGVmYXVsdCByb3V0ZSBtYXRjaGVzIG9uZSBvZiB0aGUgcm91dGVzIGRlZmluZWQgaW4gbS5yb3V0ZVwiKTtcclxuXHRcdFx0XHRcdGlzRGVmYXVsdFJvdXRlID0gdHJ1ZTtcclxuXHRcdFx0XHRcdG0ucm91dGUoYXJnMSwgdHJ1ZSk7XHJcblx0XHRcdFx0XHRpc0RlZmF1bHRSb3V0ZSA9IGZhbHNlO1xyXG5cdFx0XHRcdH1cclxuXHRcdFx0fTtcclxuXHRcdFx0dmFyIGxpc3RlbmVyID0gbS5yb3V0ZS5tb2RlID09PSBcImhhc2hcIiA/IFwib25oYXNoY2hhbmdlXCIgOiBcIm9ucG9wc3RhdGVcIjtcclxuXHRcdFx0d2luZG93W2xpc3RlbmVyXSA9IGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRcdHZhciBwYXRoID0gJGxvY2F0aW9uW20ucm91dGUubW9kZV07XHJcblx0XHRcdFx0aWYgKG0ucm91dGUubW9kZSA9PT0gXCJwYXRobmFtZVwiKSBwYXRoICs9ICRsb2NhdGlvbi5zZWFyY2g7XHJcblx0XHRcdFx0aWYgKGN1cnJlbnRSb3V0ZSAhPT0gbm9ybWFsaXplUm91dGUocGF0aCkpIHJlZGlyZWN0KHBhdGgpO1xyXG5cdFx0XHR9O1xyXG5cclxuXHRcdFx0Y29tcHV0ZVByZVJlZHJhd0hvb2sgPSBzZXRTY3JvbGw7XHJcblx0XHRcdHdpbmRvd1tsaXN0ZW5lcl0oKTtcclxuXHRcdH1cclxuXHRcdC8vY29uZmlnOiBtLnJvdXRlXHJcblx0XHRlbHNlIGlmIChyb290LmFkZEV2ZW50TGlzdGVuZXIgfHwgcm9vdC5hdHRhY2hFdmVudCkge1xyXG5cdFx0XHRyb290LmhyZWYgPSAobS5yb3V0ZS5tb2RlICE9PSAncGF0aG5hbWUnID8gJGxvY2F0aW9uLnBhdGhuYW1lIDogJycpICsgbW9kZXNbbS5yb3V0ZS5tb2RlXSArIHZkb20uYXR0cnMuaHJlZjtcclxuXHRcdFx0aWYgKHJvb3QuYWRkRXZlbnRMaXN0ZW5lcikge1xyXG5cdFx0XHRcdHJvb3QucmVtb3ZlRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHJvdXRlVW5vYnRydXNpdmUpO1xyXG5cdFx0XHRcdHJvb3QuYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHJvdXRlVW5vYnRydXNpdmUpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2Uge1xyXG5cdFx0XHRcdHJvb3QuZGV0YWNoRXZlbnQoXCJvbmNsaWNrXCIsIHJvdXRlVW5vYnRydXNpdmUpO1xyXG5cdFx0XHRcdHJvb3QuYXR0YWNoRXZlbnQoXCJvbmNsaWNrXCIsIHJvdXRlVW5vYnRydXNpdmUpO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblx0XHQvL20ucm91dGUocm91dGUsIHBhcmFtcywgc2hvdWxkUmVwbGFjZUhpc3RvcnlFbnRyeSlcclxuXHRcdGVsc2UgaWYgKGlzU3RyaW5nKHJvb3QpKSB7XHJcblx0XHRcdHZhciBvbGRSb3V0ZSA9IGN1cnJlbnRSb3V0ZTtcclxuXHRcdFx0Y3VycmVudFJvdXRlID0gcm9vdDtcclxuXHRcdFx0dmFyIGFyZ3MgPSBhcmcxIHx8IHt9O1xyXG5cdFx0XHR2YXIgcXVlcnlJbmRleCA9IGN1cnJlbnRSb3V0ZS5pbmRleE9mKFwiP1wiKTtcclxuXHRcdFx0dmFyIHBhcmFtcyA9IHF1ZXJ5SW5kZXggPiAtMSA/IHBhcnNlUXVlcnlTdHJpbmcoY3VycmVudFJvdXRlLnNsaWNlKHF1ZXJ5SW5kZXggKyAxKSkgOiB7fTtcclxuXHRcdFx0Zm9yICh2YXIgaSBpbiBhcmdzKSBwYXJhbXNbaV0gPSBhcmdzW2ldO1xyXG5cdFx0XHR2YXIgcXVlcnlzdHJpbmcgPSBidWlsZFF1ZXJ5U3RyaW5nKHBhcmFtcyk7XHJcblx0XHRcdHZhciBjdXJyZW50UGF0aCA9IHF1ZXJ5SW5kZXggPiAtMSA/IGN1cnJlbnRSb3V0ZS5zbGljZSgwLCBxdWVyeUluZGV4KSA6IGN1cnJlbnRSb3V0ZTtcclxuXHRcdFx0aWYgKHF1ZXJ5c3RyaW5nKSBjdXJyZW50Um91dGUgPSBjdXJyZW50UGF0aCArIChjdXJyZW50UGF0aC5pbmRleE9mKFwiP1wiKSA9PT0gLTEgPyBcIj9cIiA6IFwiJlwiKSArIHF1ZXJ5c3RyaW5nO1xyXG5cclxuXHRcdFx0dmFyIHNob3VsZFJlcGxhY2VIaXN0b3J5RW50cnkgPSAoYXJndW1lbnRzLmxlbmd0aCA9PT0gMyA/IGFyZzIgOiBhcmcxKSA9PT0gdHJ1ZSB8fCBvbGRSb3V0ZSA9PT0gcm9vdDtcclxuXHJcblx0XHRcdGlmICh3aW5kb3cuaGlzdG9yeS5wdXNoU3RhdGUpIHtcclxuXHRcdFx0XHRjb21wdXRlUHJlUmVkcmF3SG9vayA9IHNldFNjcm9sbDtcclxuXHRcdFx0XHRjb21wdXRlUG9zdFJlZHJhd0hvb2sgPSBmdW5jdGlvbigpIHtcclxuXHRcdFx0XHRcdHdpbmRvdy5oaXN0b3J5W3Nob3VsZFJlcGxhY2VIaXN0b3J5RW50cnkgPyBcInJlcGxhY2VTdGF0ZVwiIDogXCJwdXNoU3RhdGVcIl0obnVsbCwgJGRvY3VtZW50LnRpdGxlLCBtb2Rlc1ttLnJvdXRlLm1vZGVdICsgY3VycmVudFJvdXRlKTtcclxuXHRcdFx0XHR9O1xyXG5cdFx0XHRcdHJlZGlyZWN0KG1vZGVzW20ucm91dGUubW9kZV0gKyBjdXJyZW50Um91dGUpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2Uge1xyXG5cdFx0XHRcdCRsb2NhdGlvblttLnJvdXRlLm1vZGVdID0gY3VycmVudFJvdXRlO1xyXG5cdFx0XHRcdHJlZGlyZWN0KG1vZGVzW20ucm91dGUubW9kZV0gKyBjdXJyZW50Um91dGUpO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblx0fTtcclxuXHRtLnJvdXRlLnBhcmFtID0gZnVuY3Rpb24oa2V5KSB7XHJcblx0XHRpZiAoIXJvdXRlUGFyYW1zKSB0aHJvdyBuZXcgRXJyb3IoXCJZb3UgbXVzdCBjYWxsIG0ucm91dGUoZWxlbWVudCwgZGVmYXVsdFJvdXRlLCByb3V0ZXMpIGJlZm9yZSBjYWxsaW5nIG0ucm91dGUucGFyYW0oKVwiKTtcclxuXHRcdGlmKCAha2V5ICl7XHJcblx0XHRcdHJldHVybiByb3V0ZVBhcmFtcztcclxuXHRcdH1cclxuXHRcdHJldHVybiByb3V0ZVBhcmFtc1trZXldO1xyXG5cdH07XHJcblx0bS5yb3V0ZS5tb2RlID0gXCJzZWFyY2hcIjtcclxuXHRmdW5jdGlvbiBub3JtYWxpemVSb3V0ZShyb3V0ZSkge1xyXG5cdFx0cmV0dXJuIHJvdXRlLnNsaWNlKG1vZGVzW20ucm91dGUubW9kZV0ubGVuZ3RoKTtcclxuXHR9XHJcblx0ZnVuY3Rpb24gcm91dGVCeVZhbHVlKHJvb3QsIHJvdXRlciwgcGF0aCkge1xyXG5cdFx0cm91dGVQYXJhbXMgPSB7fTtcclxuXHJcblx0XHR2YXIgcXVlcnlTdGFydCA9IHBhdGguaW5kZXhPZihcIj9cIik7XHJcblx0XHRpZiAocXVlcnlTdGFydCAhPT0gLTEpIHtcclxuXHRcdFx0cm91dGVQYXJhbXMgPSBwYXJzZVF1ZXJ5U3RyaW5nKHBhdGguc3Vic3RyKHF1ZXJ5U3RhcnQgKyAxLCBwYXRoLmxlbmd0aCkpO1xyXG5cdFx0XHRwYXRoID0gcGF0aC5zdWJzdHIoMCwgcXVlcnlTdGFydCk7XHJcblx0XHR9XHJcblxyXG5cdFx0Ly8gR2V0IGFsbCByb3V0ZXMgYW5kIGNoZWNrIGlmIHRoZXJlJ3NcclxuXHRcdC8vIGFuIGV4YWN0IG1hdGNoIGZvciB0aGUgY3VycmVudCBwYXRoXHJcblx0XHR2YXIga2V5cyA9IE9iamVjdC5rZXlzKHJvdXRlcik7XHJcblx0XHR2YXIgaW5kZXggPSBrZXlzLmluZGV4T2YocGF0aCk7XHJcblx0XHRpZihpbmRleCAhPT0gLTEpe1xyXG5cdFx0XHRtLm1vdW50KHJvb3QsIHJvdXRlcltrZXlzIFtpbmRleF1dKTtcclxuXHRcdFx0cmV0dXJuIHRydWU7XHJcblx0XHR9XHJcblxyXG5cdFx0Zm9yICh2YXIgcm91dGUgaW4gcm91dGVyKSB7XHJcblx0XHRcdGlmIChyb3V0ZSA9PT0gcGF0aCkge1xyXG5cdFx0XHRcdG0ubW91bnQocm9vdCwgcm91dGVyW3JvdXRlXSk7XHJcblx0XHRcdFx0cmV0dXJuIHRydWU7XHJcblx0XHRcdH1cclxuXHJcblx0XHRcdHZhciBtYXRjaGVyID0gbmV3IFJlZ0V4cChcIl5cIiArIHJvdXRlLnJlcGxhY2UoLzpbXlxcL10rP1xcLnszfS9nLCBcIiguKj8pXCIpLnJlcGxhY2UoLzpbXlxcL10rL2csIFwiKFteXFxcXC9dKylcIikgKyBcIlxcLz8kXCIpO1xyXG5cclxuXHRcdFx0aWYgKG1hdGNoZXIudGVzdChwYXRoKSkge1xyXG5cdFx0XHRcdHBhdGgucmVwbGFjZShtYXRjaGVyLCBmdW5jdGlvbigpIHtcclxuXHRcdFx0XHRcdHZhciBrZXlzID0gcm91dGUubWF0Y2goLzpbXlxcL10rL2cpIHx8IFtdO1xyXG5cdFx0XHRcdFx0dmFyIHZhbHVlcyA9IFtdLnNsaWNlLmNhbGwoYXJndW1lbnRzLCAxLCAtMik7XHJcblx0XHRcdFx0XHRmb3JFYWNoKGtleXMsIGZ1bmN0aW9uIChrZXksIGkpIHtcclxuXHRcdFx0XHRcdFx0cm91dGVQYXJhbXNba2V5LnJlcGxhY2UoLzp8XFwuL2csIFwiXCIpXSA9IGRlY29kZVVSSUNvbXBvbmVudCh2YWx1ZXNbaV0pO1xyXG5cdFx0XHRcdFx0fSlcclxuXHRcdFx0XHRcdG0ubW91bnQocm9vdCwgcm91dGVyW3JvdXRlXSk7XHJcblx0XHRcdFx0fSk7XHJcblx0XHRcdFx0cmV0dXJuIHRydWU7XHJcblx0XHRcdH1cclxuXHRcdH1cclxuXHR9XHJcblx0ZnVuY3Rpb24gcm91dGVVbm9idHJ1c2l2ZShlKSB7XHJcblx0XHRlID0gZSB8fCBldmVudDtcclxuXHJcblx0XHRpZiAoZS5jdHJsS2V5IHx8IGUubWV0YUtleSB8fCBlLndoaWNoID09PSAyKSByZXR1cm47XHJcblxyXG5cdFx0aWYgKGUucHJldmVudERlZmF1bHQpIGUucHJldmVudERlZmF1bHQoKTtcclxuXHRcdGVsc2UgZS5yZXR1cm5WYWx1ZSA9IGZhbHNlO1xyXG5cclxuXHRcdHZhciBjdXJyZW50VGFyZ2V0ID0gZS5jdXJyZW50VGFyZ2V0IHx8IGUuc3JjRWxlbWVudDtcclxuXHRcdHZhciBhcmdzID0gbS5yb3V0ZS5tb2RlID09PSBcInBhdGhuYW1lXCIgJiYgY3VycmVudFRhcmdldC5zZWFyY2ggPyBwYXJzZVF1ZXJ5U3RyaW5nKGN1cnJlbnRUYXJnZXQuc2VhcmNoLnNsaWNlKDEpKSA6IHt9O1xyXG5cdFx0d2hpbGUgKGN1cnJlbnRUYXJnZXQgJiYgY3VycmVudFRhcmdldC5ub2RlTmFtZS50b1VwcGVyQ2FzZSgpICE9PSBcIkFcIikgY3VycmVudFRhcmdldCA9IGN1cnJlbnRUYXJnZXQucGFyZW50Tm9kZTtcclxuXHRcdG0ucm91dGUoY3VycmVudFRhcmdldFttLnJvdXRlLm1vZGVdLnNsaWNlKG1vZGVzW20ucm91dGUubW9kZV0ubGVuZ3RoKSwgYXJncyk7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIHNldFNjcm9sbCgpIHtcclxuXHRcdGlmIChtLnJvdXRlLm1vZGUgIT09IFwiaGFzaFwiICYmICRsb2NhdGlvbi5oYXNoKSAkbG9jYXRpb24uaGFzaCA9ICRsb2NhdGlvbi5oYXNoO1xyXG5cdFx0ZWxzZSB3aW5kb3cuc2Nyb2xsVG8oMCwgMCk7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIGJ1aWxkUXVlcnlTdHJpbmcob2JqZWN0LCBwcmVmaXgpIHtcclxuXHRcdHZhciBkdXBsaWNhdGVzID0ge307XHJcblx0XHR2YXIgc3RyID0gW107XHJcblx0XHRmb3IgKHZhciBwcm9wIGluIG9iamVjdCkge1xyXG5cdFx0XHR2YXIga2V5ID0gcHJlZml4ID8gcHJlZml4ICsgXCJbXCIgKyBwcm9wICsgXCJdXCIgOiBwcm9wO1xyXG5cdFx0XHR2YXIgdmFsdWUgPSBvYmplY3RbcHJvcF07XHJcblxyXG5cdFx0XHRpZiAodmFsdWUgPT09IG51bGwpIHtcclxuXHRcdFx0XHRzdHIucHVzaChlbmNvZGVVUklDb21wb25lbnQoa2V5KSk7XHJcblx0XHRcdH0gZWxzZSBpZiAoaXNPYmplY3QodmFsdWUpKSB7XHJcblx0XHRcdFx0c3RyLnB1c2goYnVpbGRRdWVyeVN0cmluZyh2YWx1ZSwga2V5KSk7XHJcblx0XHRcdH0gZWxzZSBpZiAoaXNBcnJheSh2YWx1ZSkpIHtcclxuXHRcdFx0XHR2YXIga2V5cyA9IFtdO1xyXG5cdFx0XHRcdGR1cGxpY2F0ZXNba2V5XSA9IGR1cGxpY2F0ZXNba2V5XSB8fCB7fTtcclxuXHRcdFx0XHRmb3JFYWNoKHZhbHVlLCBmdW5jdGlvbiAoaXRlbSkge1xyXG5cdFx0XHRcdFx0aWYgKCFkdXBsaWNhdGVzW2tleV1baXRlbV0pIHtcclxuXHRcdFx0XHRcdFx0ZHVwbGljYXRlc1trZXldW2l0ZW1dID0gdHJ1ZTtcclxuXHRcdFx0XHRcdFx0a2V5cy5wdXNoKGVuY29kZVVSSUNvbXBvbmVudChrZXkpICsgXCI9XCIgKyBlbmNvZGVVUklDb21wb25lbnQoaXRlbSkpO1xyXG5cdFx0XHRcdFx0fVxyXG5cdFx0XHRcdH0pO1xyXG5cdFx0XHRcdHN0ci5wdXNoKGtleXMuam9pbihcIiZcIikpO1xyXG5cdFx0XHR9IGVsc2UgaWYgKHZhbHVlICE9PSB1bmRlZmluZWQpIHtcclxuXHRcdFx0XHRzdHIucHVzaChlbmNvZGVVUklDb21wb25lbnQoa2V5KSArIFwiPVwiICsgZW5jb2RlVVJJQ29tcG9uZW50KHZhbHVlKSk7XHJcblx0XHRcdH1cclxuXHRcdH1cclxuXHRcdHJldHVybiBzdHIuam9pbihcIiZcIik7XHJcblx0fVxyXG5cdGZ1bmN0aW9uIHBhcnNlUXVlcnlTdHJpbmcoc3RyKSB7XHJcblx0XHRpZiAoc3RyID09PSBcIlwiIHx8IHN0ciA9PSBudWxsKSByZXR1cm4ge307XHJcblx0XHRpZiAoc3RyLmNoYXJBdCgwKSA9PT0gXCI/XCIpIHN0ciA9IHN0ci5zbGljZSgxKTtcclxuXHJcblx0XHR2YXIgcGFpcnMgPSBzdHIuc3BsaXQoXCImXCIpLCBwYXJhbXMgPSB7fTtcclxuXHRcdGZvckVhY2gocGFpcnMsIGZ1bmN0aW9uIChzdHJpbmcpIHtcclxuXHRcdFx0dmFyIHBhaXIgPSBzdHJpbmcuc3BsaXQoXCI9XCIpO1xyXG5cdFx0XHR2YXIga2V5ID0gZGVjb2RlVVJJQ29tcG9uZW50KHBhaXJbMF0pO1xyXG5cdFx0XHR2YXIgdmFsdWUgPSBwYWlyLmxlbmd0aCA9PT0gMiA/IGRlY29kZVVSSUNvbXBvbmVudChwYWlyWzFdKSA6IG51bGw7XHJcblx0XHRcdGlmIChwYXJhbXNba2V5XSAhPSBudWxsKSB7XHJcblx0XHRcdFx0aWYgKCFpc0FycmF5KHBhcmFtc1trZXldKSkgcGFyYW1zW2tleV0gPSBbcGFyYW1zW2tleV1dO1xyXG5cdFx0XHRcdHBhcmFtc1trZXldLnB1c2godmFsdWUpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2UgcGFyYW1zW2tleV0gPSB2YWx1ZTtcclxuXHRcdH0pO1xyXG5cclxuXHRcdHJldHVybiBwYXJhbXM7XHJcblx0fVxyXG5cdG0ucm91dGUuYnVpbGRRdWVyeVN0cmluZyA9IGJ1aWxkUXVlcnlTdHJpbmc7XHJcblx0bS5yb3V0ZS5wYXJzZVF1ZXJ5U3RyaW5nID0gcGFyc2VRdWVyeVN0cmluZztcclxuXHJcblx0ZnVuY3Rpb24gcmVzZXQocm9vdCkge1xyXG5cdFx0dmFyIGNhY2hlS2V5ID0gZ2V0Q2VsbENhY2hlS2V5KHJvb3QpO1xyXG5cdFx0Y2xlYXIocm9vdC5jaGlsZE5vZGVzLCBjZWxsQ2FjaGVbY2FjaGVLZXldKTtcclxuXHRcdGNlbGxDYWNoZVtjYWNoZUtleV0gPSB1bmRlZmluZWQ7XHJcblx0fVxyXG5cclxuXHRtLmRlZmVycmVkID0gZnVuY3Rpb24gKCkge1xyXG5cdFx0dmFyIGRlZmVycmVkID0gbmV3IERlZmVycmVkKCk7XHJcblx0XHRkZWZlcnJlZC5wcm9taXNlID0gcHJvcGlmeShkZWZlcnJlZC5wcm9taXNlKTtcclxuXHRcdHJldHVybiBkZWZlcnJlZDtcclxuXHR9O1xyXG5cdGZ1bmN0aW9uIHByb3BpZnkocHJvbWlzZSwgaW5pdGlhbFZhbHVlKSB7XHJcblx0XHR2YXIgcHJvcCA9IG0ucHJvcChpbml0aWFsVmFsdWUpO1xyXG5cdFx0cHJvbWlzZS50aGVuKHByb3ApO1xyXG5cdFx0cHJvcC50aGVuID0gZnVuY3Rpb24ocmVzb2x2ZSwgcmVqZWN0KSB7XHJcblx0XHRcdHJldHVybiBwcm9waWZ5KHByb21pc2UudGhlbihyZXNvbHZlLCByZWplY3QpLCBpbml0aWFsVmFsdWUpO1xyXG5cdFx0fTtcclxuXHRcdHByb3BbXCJjYXRjaFwiXSA9IHByb3AudGhlbi5iaW5kKG51bGwsIG51bGwpO1xyXG5cdFx0cHJvcFtcImZpbmFsbHlcIl0gPSBmdW5jdGlvbihjYWxsYmFjaykge1xyXG5cdFx0XHR2YXIgX2NhbGxiYWNrID0gZnVuY3Rpb24oKSB7cmV0dXJuIG0uZGVmZXJyZWQoKS5yZXNvbHZlKGNhbGxiYWNrKCkpLnByb21pc2U7fTtcclxuXHRcdFx0cmV0dXJuIHByb3AudGhlbihmdW5jdGlvbih2YWx1ZSkge1xyXG5cdFx0XHRcdHJldHVybiBwcm9waWZ5KF9jYWxsYmFjaygpLnRoZW4oZnVuY3Rpb24oKSB7cmV0dXJuIHZhbHVlO30pLCBpbml0aWFsVmFsdWUpO1xyXG5cdFx0XHR9LCBmdW5jdGlvbihyZWFzb24pIHtcclxuXHRcdFx0XHRyZXR1cm4gcHJvcGlmeShfY2FsbGJhY2soKS50aGVuKGZ1bmN0aW9uKCkge3Rocm93IG5ldyBFcnJvcihyZWFzb24pO30pLCBpbml0aWFsVmFsdWUpO1xyXG5cdFx0XHR9KTtcclxuXHRcdH07XHJcblx0XHRyZXR1cm4gcHJvcDtcclxuXHR9XHJcblx0Ly9Qcm9taXoubWl0aHJpbC5qcyB8IFpvbG1laXN0ZXIgfCBNSVRcclxuXHQvL2EgbW9kaWZpZWQgdmVyc2lvbiBvZiBQcm9taXouanMsIHdoaWNoIGRvZXMgbm90IGNvbmZvcm0gdG8gUHJvbWlzZXMvQSsgZm9yIHR3byByZWFzb25zOlxyXG5cdC8vMSkgYHRoZW5gIGNhbGxiYWNrcyBhcmUgY2FsbGVkIHN5bmNocm9ub3VzbHkgKGJlY2F1c2Ugc2V0VGltZW91dCBpcyB0b28gc2xvdywgYW5kIHRoZSBzZXRJbW1lZGlhdGUgcG9seWZpbGwgaXMgdG9vIGJpZ1xyXG5cdC8vMikgdGhyb3dpbmcgc3ViY2xhc3NlcyBvZiBFcnJvciBjYXVzZSB0aGUgZXJyb3IgdG8gYmUgYnViYmxlZCB1cCBpbnN0ZWFkIG9mIHRyaWdnZXJpbmcgcmVqZWN0aW9uIChiZWNhdXNlIHRoZSBzcGVjIGRvZXMgbm90IGFjY291bnQgZm9yIHRoZSBpbXBvcnRhbnQgdXNlIGNhc2Ugb2YgZGVmYXVsdCBicm93c2VyIGVycm9yIGhhbmRsaW5nLCBpLmUuIG1lc3NhZ2Ugdy8gbGluZSBudW1iZXIpXHJcblx0ZnVuY3Rpb24gRGVmZXJyZWQoc3VjY2Vzc0NhbGxiYWNrLCBmYWlsdXJlQ2FsbGJhY2spIHtcclxuXHRcdHZhciBSRVNPTFZJTkcgPSAxLCBSRUpFQ1RJTkcgPSAyLCBSRVNPTFZFRCA9IDMsIFJFSkVDVEVEID0gNDtcclxuXHRcdHZhciBzZWxmID0gdGhpcywgc3RhdGUgPSAwLCBwcm9taXNlVmFsdWUgPSAwLCBuZXh0ID0gW107XHJcblxyXG5cdFx0c2VsZi5wcm9taXNlID0ge307XHJcblxyXG5cdFx0c2VsZi5yZXNvbHZlID0gZnVuY3Rpb24odmFsdWUpIHtcclxuXHRcdFx0aWYgKCFzdGF0ZSkge1xyXG5cdFx0XHRcdHByb21pc2VWYWx1ZSA9IHZhbHVlO1xyXG5cdFx0XHRcdHN0YXRlID0gUkVTT0xWSU5HO1xyXG5cclxuXHRcdFx0XHRmaXJlKCk7XHJcblx0XHRcdH1cclxuXHRcdFx0cmV0dXJuIHRoaXM7XHJcblx0XHR9O1xyXG5cclxuXHRcdHNlbGYucmVqZWN0ID0gZnVuY3Rpb24odmFsdWUpIHtcclxuXHRcdFx0aWYgKCFzdGF0ZSkge1xyXG5cdFx0XHRcdHByb21pc2VWYWx1ZSA9IHZhbHVlO1xyXG5cdFx0XHRcdHN0YXRlID0gUkVKRUNUSU5HO1xyXG5cclxuXHRcdFx0XHRmaXJlKCk7XHJcblx0XHRcdH1cclxuXHRcdFx0cmV0dXJuIHRoaXM7XHJcblx0XHR9O1xyXG5cclxuXHRcdHNlbGYucHJvbWlzZS50aGVuID0gZnVuY3Rpb24oc3VjY2Vzc0NhbGxiYWNrLCBmYWlsdXJlQ2FsbGJhY2spIHtcclxuXHRcdFx0dmFyIGRlZmVycmVkID0gbmV3IERlZmVycmVkKHN1Y2Nlc3NDYWxsYmFjaywgZmFpbHVyZUNhbGxiYWNrKVxyXG5cdFx0XHRpZiAoc3RhdGUgPT09IFJFU09MVkVEKSB7XHJcblx0XHRcdFx0ZGVmZXJyZWQucmVzb2x2ZShwcm9taXNlVmFsdWUpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2UgaWYgKHN0YXRlID09PSBSRUpFQ1RFRCkge1xyXG5cdFx0XHRcdGRlZmVycmVkLnJlamVjdChwcm9taXNlVmFsdWUpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGVsc2Uge1xyXG5cdFx0XHRcdG5leHQucHVzaChkZWZlcnJlZCk7XHJcblx0XHRcdH1cclxuXHRcdFx0cmV0dXJuIGRlZmVycmVkLnByb21pc2VcclxuXHRcdH07XHJcblxyXG5cdFx0ZnVuY3Rpb24gZmluaXNoKHR5cGUpIHtcclxuXHRcdFx0c3RhdGUgPSB0eXBlIHx8IFJFSkVDVEVEO1xyXG5cdFx0XHRuZXh0Lm1hcChmdW5jdGlvbihkZWZlcnJlZCkge1xyXG5cdFx0XHRcdHN0YXRlID09PSBSRVNPTFZFRCA/IGRlZmVycmVkLnJlc29sdmUocHJvbWlzZVZhbHVlKSA6IGRlZmVycmVkLnJlamVjdChwcm9taXNlVmFsdWUpO1xyXG5cdFx0XHR9KTtcclxuXHRcdH1cclxuXHJcblx0XHRmdW5jdGlvbiB0aGVubmFibGUodGhlbiwgc3VjY2Vzc0NhbGxiYWNrLCBmYWlsdXJlQ2FsbGJhY2ssIG5vdFRoZW5uYWJsZUNhbGxiYWNrKSB7XHJcblx0XHRcdGlmICgoKHByb21pc2VWYWx1ZSAhPSBudWxsICYmIGlzT2JqZWN0KHByb21pc2VWYWx1ZSkpIHx8IGlzRnVuY3Rpb24ocHJvbWlzZVZhbHVlKSkgJiYgaXNGdW5jdGlvbih0aGVuKSkge1xyXG5cdFx0XHRcdHRyeSB7XHJcblx0XHRcdFx0XHQvLyBjb3VudCBwcm90ZWN0cyBhZ2FpbnN0IGFidXNlIGNhbGxzIGZyb20gc3BlYyBjaGVja2VyXHJcblx0XHRcdFx0XHR2YXIgY291bnQgPSAwO1xyXG5cdFx0XHRcdFx0dGhlbi5jYWxsKHByb21pc2VWYWx1ZSwgZnVuY3Rpb24odmFsdWUpIHtcclxuXHRcdFx0XHRcdFx0aWYgKGNvdW50KyspIHJldHVybjtcclxuXHRcdFx0XHRcdFx0cHJvbWlzZVZhbHVlID0gdmFsdWU7XHJcblx0XHRcdFx0XHRcdHN1Y2Nlc3NDYWxsYmFjaygpO1xyXG5cdFx0XHRcdFx0fSwgZnVuY3Rpb24gKHZhbHVlKSB7XHJcblx0XHRcdFx0XHRcdGlmIChjb3VudCsrKSByZXR1cm47XHJcblx0XHRcdFx0XHRcdHByb21pc2VWYWx1ZSA9IHZhbHVlO1xyXG5cdFx0XHRcdFx0XHRmYWlsdXJlQ2FsbGJhY2soKTtcclxuXHRcdFx0XHRcdH0pO1xyXG5cdFx0XHRcdH1cclxuXHRcdFx0XHRjYXRjaCAoZSkge1xyXG5cdFx0XHRcdFx0bS5kZWZlcnJlZC5vbmVycm9yKGUpO1xyXG5cdFx0XHRcdFx0cHJvbWlzZVZhbHVlID0gZTtcclxuXHRcdFx0XHRcdGZhaWx1cmVDYWxsYmFjaygpO1xyXG5cdFx0XHRcdH1cclxuXHRcdFx0fSBlbHNlIHtcclxuXHRcdFx0XHRub3RUaGVubmFibGVDYWxsYmFjaygpO1xyXG5cdFx0XHR9XHJcblx0XHR9XHJcblxyXG5cdFx0ZnVuY3Rpb24gZmlyZSgpIHtcclxuXHRcdFx0Ly8gY2hlY2sgaWYgaXQncyBhIHRoZW5hYmxlXHJcblx0XHRcdHZhciB0aGVuO1xyXG5cdFx0XHR0cnkge1xyXG5cdFx0XHRcdHRoZW4gPSBwcm9taXNlVmFsdWUgJiYgcHJvbWlzZVZhbHVlLnRoZW47XHJcblx0XHRcdH1cclxuXHRcdFx0Y2F0Y2ggKGUpIHtcclxuXHRcdFx0XHRtLmRlZmVycmVkLm9uZXJyb3IoZSk7XHJcblx0XHRcdFx0cHJvbWlzZVZhbHVlID0gZTtcclxuXHRcdFx0XHRzdGF0ZSA9IFJFSkVDVElORztcclxuXHRcdFx0XHRyZXR1cm4gZmlyZSgpO1xyXG5cdFx0XHR9XHJcblxyXG5cdFx0XHR0aGVubmFibGUodGhlbiwgZnVuY3Rpb24oKSB7XHJcblx0XHRcdFx0c3RhdGUgPSBSRVNPTFZJTkc7XHJcblx0XHRcdFx0ZmlyZSgpO1xyXG5cdFx0XHR9LCBmdW5jdGlvbigpIHtcclxuXHRcdFx0XHRzdGF0ZSA9IFJFSkVDVElORztcclxuXHRcdFx0XHRmaXJlKCk7XHJcblx0XHRcdH0sIGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRcdHRyeSB7XHJcblx0XHRcdFx0XHRpZiAoc3RhdGUgPT09IFJFU09MVklORyAmJiBpc0Z1bmN0aW9uKHN1Y2Nlc3NDYWxsYmFjaykpIHtcclxuXHRcdFx0XHRcdFx0cHJvbWlzZVZhbHVlID0gc3VjY2Vzc0NhbGxiYWNrKHByb21pc2VWYWx1ZSk7XHJcblx0XHRcdFx0XHR9XHJcblx0XHRcdFx0XHRlbHNlIGlmIChzdGF0ZSA9PT0gUkVKRUNUSU5HICYmIGlzRnVuY3Rpb24oZmFpbHVyZUNhbGxiYWNrKSkge1xyXG5cdFx0XHRcdFx0XHRwcm9taXNlVmFsdWUgPSBmYWlsdXJlQ2FsbGJhY2socHJvbWlzZVZhbHVlKTtcclxuXHRcdFx0XHRcdFx0c3RhdGUgPSBSRVNPTFZJTkc7XHJcblx0XHRcdFx0XHR9XHJcblx0XHRcdFx0fVxyXG5cdFx0XHRcdGNhdGNoIChlKSB7XHJcblx0XHRcdFx0XHRtLmRlZmVycmVkLm9uZXJyb3IoZSk7XHJcblx0XHRcdFx0XHRwcm9taXNlVmFsdWUgPSBlO1xyXG5cdFx0XHRcdFx0cmV0dXJuIGZpbmlzaCgpO1xyXG5cdFx0XHRcdH1cclxuXHJcblx0XHRcdFx0aWYgKHByb21pc2VWYWx1ZSA9PT0gc2VsZikge1xyXG5cdFx0XHRcdFx0cHJvbWlzZVZhbHVlID0gVHlwZUVycm9yKCk7XHJcblx0XHRcdFx0XHRmaW5pc2goKTtcclxuXHRcdFx0XHR9IGVsc2Uge1xyXG5cdFx0XHRcdFx0dGhlbm5hYmxlKHRoZW4sIGZ1bmN0aW9uICgpIHtcclxuXHRcdFx0XHRcdFx0ZmluaXNoKFJFU09MVkVEKTtcclxuXHRcdFx0XHRcdH0sIGZpbmlzaCwgZnVuY3Rpb24gKCkge1xyXG5cdFx0XHRcdFx0XHRmaW5pc2goc3RhdGUgPT09IFJFU09MVklORyAmJiBSRVNPTFZFRCk7XHJcblx0XHRcdFx0XHR9KTtcclxuXHRcdFx0XHR9XHJcblx0XHRcdH0pO1xyXG5cdFx0fVxyXG5cdH1cclxuXHRtLmRlZmVycmVkLm9uZXJyb3IgPSBmdW5jdGlvbihlKSB7XHJcblx0XHRpZiAodHlwZS5jYWxsKGUpID09PSBcIltvYmplY3QgRXJyb3JdXCIgJiYgIWUuY29uc3RydWN0b3IudG9TdHJpbmcoKS5tYXRjaCgvIEVycm9yLykpIHtcclxuXHRcdFx0cGVuZGluZ1JlcXVlc3RzID0gMDtcclxuXHRcdFx0dGhyb3cgZTtcclxuXHRcdH1cclxuXHR9O1xyXG5cclxuXHRtLnN5bmMgPSBmdW5jdGlvbihhcmdzKSB7XHJcblx0XHR2YXIgbWV0aG9kID0gXCJyZXNvbHZlXCI7XHJcblxyXG5cdFx0ZnVuY3Rpb24gc3luY2hyb25pemVyKHBvcywgcmVzb2x2ZWQpIHtcclxuXHRcdFx0cmV0dXJuIGZ1bmN0aW9uKHZhbHVlKSB7XHJcblx0XHRcdFx0cmVzdWx0c1twb3NdID0gdmFsdWU7XHJcblx0XHRcdFx0aWYgKCFyZXNvbHZlZCkgbWV0aG9kID0gXCJyZWplY3RcIjtcclxuXHRcdFx0XHRpZiAoLS1vdXRzdGFuZGluZyA9PT0gMCkge1xyXG5cdFx0XHRcdFx0ZGVmZXJyZWQucHJvbWlzZShyZXN1bHRzKTtcclxuXHRcdFx0XHRcdGRlZmVycmVkW21ldGhvZF0ocmVzdWx0cyk7XHJcblx0XHRcdFx0fVxyXG5cdFx0XHRcdHJldHVybiB2YWx1ZTtcclxuXHRcdFx0fTtcclxuXHRcdH1cclxuXHJcblx0XHR2YXIgZGVmZXJyZWQgPSBtLmRlZmVycmVkKCk7XHJcblx0XHR2YXIgb3V0c3RhbmRpbmcgPSBhcmdzLmxlbmd0aDtcclxuXHRcdHZhciByZXN1bHRzID0gbmV3IEFycmF5KG91dHN0YW5kaW5nKTtcclxuXHRcdGlmIChhcmdzLmxlbmd0aCA+IDApIHtcclxuXHRcdFx0Zm9yRWFjaChhcmdzLCBmdW5jdGlvbiAoYXJnLCBpKSB7XHJcblx0XHRcdFx0YXJnLnRoZW4oc3luY2hyb25pemVyKGksIHRydWUpLCBzeW5jaHJvbml6ZXIoaSwgZmFsc2UpKTtcclxuXHRcdFx0fSk7XHJcblx0XHR9XHJcblx0XHRlbHNlIGRlZmVycmVkLnJlc29sdmUoW10pO1xyXG5cclxuXHRcdHJldHVybiBkZWZlcnJlZC5wcm9taXNlO1xyXG5cdH07XHJcblx0ZnVuY3Rpb24gaWRlbnRpdHkodmFsdWUpIHsgcmV0dXJuIHZhbHVlOyB9XHJcblxyXG5cdGZ1bmN0aW9uIGFqYXgob3B0aW9ucykge1xyXG5cdFx0aWYgKG9wdGlvbnMuZGF0YVR5cGUgJiYgb3B0aW9ucy5kYXRhVHlwZS50b0xvd2VyQ2FzZSgpID09PSBcImpzb25wXCIpIHtcclxuXHRcdFx0dmFyIGNhbGxiYWNrS2V5ID0gXCJtaXRocmlsX2NhbGxiYWNrX1wiICsgbmV3IERhdGUoKS5nZXRUaW1lKCkgKyBcIl9cIiArIChNYXRoLnJvdW5kKE1hdGgucmFuZG9tKCkgKiAxZTE2KSkudG9TdHJpbmcoMzYpXHJcblx0XHRcdHZhciBzY3JpcHQgPSAkZG9jdW1lbnQuY3JlYXRlRWxlbWVudChcInNjcmlwdFwiKTtcclxuXHJcblx0XHRcdHdpbmRvd1tjYWxsYmFja0tleV0gPSBmdW5jdGlvbihyZXNwKSB7XHJcblx0XHRcdFx0c2NyaXB0LnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQoc2NyaXB0KTtcclxuXHRcdFx0XHRvcHRpb25zLm9ubG9hZCh7XHJcblx0XHRcdFx0XHR0eXBlOiBcImxvYWRcIixcclxuXHRcdFx0XHRcdHRhcmdldDoge1xyXG5cdFx0XHRcdFx0XHRyZXNwb25zZVRleHQ6IHJlc3BcclxuXHRcdFx0XHRcdH1cclxuXHRcdFx0XHR9KTtcclxuXHRcdFx0XHR3aW5kb3dbY2FsbGJhY2tLZXldID0gdW5kZWZpbmVkO1xyXG5cdFx0XHR9O1xyXG5cclxuXHRcdFx0c2NyaXB0Lm9uZXJyb3IgPSBmdW5jdGlvbigpIHtcclxuXHRcdFx0XHRzY3JpcHQucGFyZW50Tm9kZS5yZW1vdmVDaGlsZChzY3JpcHQpO1xyXG5cclxuXHRcdFx0XHRvcHRpb25zLm9uZXJyb3Ioe1xyXG5cdFx0XHRcdFx0dHlwZTogXCJlcnJvclwiLFxyXG5cdFx0XHRcdFx0dGFyZ2V0OiB7XHJcblx0XHRcdFx0XHRcdHN0YXR1czogNTAwLFxyXG5cdFx0XHRcdFx0XHRyZXNwb25zZVRleHQ6IEpTT04uc3RyaW5naWZ5KHtcclxuXHRcdFx0XHRcdFx0XHRlcnJvcjogXCJFcnJvciBtYWtpbmcganNvbnAgcmVxdWVzdFwiXHJcblx0XHRcdFx0XHRcdH0pXHJcblx0XHRcdFx0XHR9XHJcblx0XHRcdFx0fSk7XHJcblx0XHRcdFx0d2luZG93W2NhbGxiYWNrS2V5XSA9IHVuZGVmaW5lZDtcclxuXHJcblx0XHRcdFx0cmV0dXJuIGZhbHNlO1xyXG5cdFx0XHR9XHJcblxyXG5cdFx0XHRzY3JpcHQub25sb2FkID0gZnVuY3Rpb24oKSB7XHJcblx0XHRcdFx0cmV0dXJuIGZhbHNlO1xyXG5cdFx0XHR9O1xyXG5cclxuXHRcdFx0c2NyaXB0LnNyYyA9IG9wdGlvbnMudXJsXHJcblx0XHRcdFx0KyAob3B0aW9ucy51cmwuaW5kZXhPZihcIj9cIikgPiAwID8gXCImXCIgOiBcIj9cIilcclxuXHRcdFx0XHQrIChvcHRpb25zLmNhbGxiYWNrS2V5ID8gb3B0aW9ucy5jYWxsYmFja0tleSA6IFwiY2FsbGJhY2tcIilcclxuXHRcdFx0XHQrIFwiPVwiICsgY2FsbGJhY2tLZXlcclxuXHRcdFx0XHQrIFwiJlwiICsgYnVpbGRRdWVyeVN0cmluZyhvcHRpb25zLmRhdGEgfHwge30pO1xyXG5cdFx0XHQkZG9jdW1lbnQuYm9keS5hcHBlbmRDaGlsZChzY3JpcHQpO1xyXG5cdFx0fVxyXG5cdFx0ZWxzZSB7XHJcblx0XHRcdHZhciB4aHIgPSBuZXcgd2luZG93LlhNTEh0dHBSZXF1ZXN0KCk7XHJcblx0XHRcdHhoci5vcGVuKG9wdGlvbnMubWV0aG9kLCBvcHRpb25zLnVybCwgdHJ1ZSwgb3B0aW9ucy51c2VyLCBvcHRpb25zLnBhc3N3b3JkKTtcclxuXHRcdFx0eGhyLm9ucmVhZHlzdGF0ZWNoYW5nZSA9IGZ1bmN0aW9uKCkge1xyXG5cdFx0XHRcdGlmICh4aHIucmVhZHlTdGF0ZSA9PT0gNCkge1xyXG5cdFx0XHRcdFx0aWYgKHhoci5zdGF0dXMgPj0gMjAwICYmIHhoci5zdGF0dXMgPCAzMDApIG9wdGlvbnMub25sb2FkKHt0eXBlOiBcImxvYWRcIiwgdGFyZ2V0OiB4aHJ9KTtcclxuXHRcdFx0XHRcdGVsc2Ugb3B0aW9ucy5vbmVycm9yKHt0eXBlOiBcImVycm9yXCIsIHRhcmdldDogeGhyfSk7XHJcblx0XHRcdFx0fVxyXG5cdFx0XHR9O1xyXG5cdFx0XHRpZiAob3B0aW9ucy5zZXJpYWxpemUgPT09IEpTT04uc3RyaW5naWZ5ICYmIG9wdGlvbnMuZGF0YSAmJiBvcHRpb25zLm1ldGhvZCAhPT0gXCJHRVRcIikge1xyXG5cdFx0XHRcdHhoci5zZXRSZXF1ZXN0SGVhZGVyKFwiQ29udGVudC1UeXBlXCIsIFwiYXBwbGljYXRpb24vanNvbjsgY2hhcnNldD11dGYtOFwiKTtcclxuXHRcdFx0fVxyXG5cdFx0XHRpZiAob3B0aW9ucy5kZXNlcmlhbGl6ZSA9PT0gSlNPTi5wYXJzZSkge1xyXG5cdFx0XHRcdHhoci5zZXRSZXF1ZXN0SGVhZGVyKFwiQWNjZXB0XCIsIFwiYXBwbGljYXRpb24vanNvbiwgdGV4dC8qXCIpO1xyXG5cdFx0XHR9XHJcblx0XHRcdGlmIChpc0Z1bmN0aW9uKG9wdGlvbnMuY29uZmlnKSkge1xyXG5cdFx0XHRcdHZhciBtYXliZVhociA9IG9wdGlvbnMuY29uZmlnKHhociwgb3B0aW9ucyk7XHJcblx0XHRcdFx0aWYgKG1heWJlWGhyICE9IG51bGwpIHhociA9IG1heWJlWGhyO1xyXG5cdFx0XHR9XHJcblxyXG5cdFx0XHR2YXIgZGF0YSA9IG9wdGlvbnMubWV0aG9kID09PSBcIkdFVFwiIHx8ICFvcHRpb25zLmRhdGEgPyBcIlwiIDogb3B0aW9ucy5kYXRhO1xyXG5cdFx0XHRpZiAoZGF0YSAmJiAoIWlzU3RyaW5nKGRhdGEpICYmIGRhdGEuY29uc3RydWN0b3IgIT09IHdpbmRvdy5Gb3JtRGF0YSkpIHtcclxuXHRcdFx0XHR0aHJvdyBuZXcgRXJyb3IoXCJSZXF1ZXN0IGRhdGEgc2hvdWxkIGJlIGVpdGhlciBiZSBhIHN0cmluZyBvciBGb3JtRGF0YS4gQ2hlY2sgdGhlIGBzZXJpYWxpemVgIG9wdGlvbiBpbiBgbS5yZXF1ZXN0YFwiKTtcclxuXHRcdFx0fVxyXG5cdFx0XHR4aHIuc2VuZChkYXRhKTtcclxuXHRcdFx0cmV0dXJuIHhocjtcclxuXHRcdH1cclxuXHR9XHJcblxyXG5cdGZ1bmN0aW9uIGJpbmREYXRhKHhock9wdGlvbnMsIGRhdGEsIHNlcmlhbGl6ZSkge1xyXG5cdFx0aWYgKHhock9wdGlvbnMubWV0aG9kID09PSBcIkdFVFwiICYmIHhock9wdGlvbnMuZGF0YVR5cGUgIT09IFwianNvbnBcIikge1xyXG5cdFx0XHR2YXIgcHJlZml4ID0geGhyT3B0aW9ucy51cmwuaW5kZXhPZihcIj9cIikgPCAwID8gXCI/XCIgOiBcIiZcIjtcclxuXHRcdFx0dmFyIHF1ZXJ5c3RyaW5nID0gYnVpbGRRdWVyeVN0cmluZyhkYXRhKTtcclxuXHRcdFx0eGhyT3B0aW9ucy51cmwgPSB4aHJPcHRpb25zLnVybCArIChxdWVyeXN0cmluZyA/IHByZWZpeCArIHF1ZXJ5c3RyaW5nIDogXCJcIik7XHJcblx0XHR9XHJcblx0XHRlbHNlIHhock9wdGlvbnMuZGF0YSA9IHNlcmlhbGl6ZShkYXRhKTtcclxuXHRcdHJldHVybiB4aHJPcHRpb25zO1xyXG5cdH1cclxuXHJcblx0ZnVuY3Rpb24gcGFyYW1ldGVyaXplVXJsKHVybCwgZGF0YSkge1xyXG5cdFx0dmFyIHRva2VucyA9IHVybC5tYXRjaCgvOlthLXpdXFx3Ky9naSk7XHJcblx0XHRpZiAodG9rZW5zICYmIGRhdGEpIHtcclxuXHRcdFx0Zm9yRWFjaCh0b2tlbnMsIGZ1bmN0aW9uICh0b2tlbikge1xyXG5cdFx0XHRcdHZhciBrZXkgPSB0b2tlbi5zbGljZSgxKTtcclxuXHRcdFx0XHR1cmwgPSB1cmwucmVwbGFjZSh0b2tlbiwgZGF0YVtrZXldKTtcclxuXHRcdFx0XHRkZWxldGUgZGF0YVtrZXldO1xyXG5cdFx0XHR9KTtcclxuXHRcdH1cclxuXHRcdHJldHVybiB1cmw7XHJcblx0fVxyXG5cclxuXHRtLnJlcXVlc3QgPSBmdW5jdGlvbih4aHJPcHRpb25zKSB7XHJcblx0XHRpZiAoeGhyT3B0aW9ucy5iYWNrZ3JvdW5kICE9PSB0cnVlKSBtLnN0YXJ0Q29tcHV0YXRpb24oKTtcclxuXHRcdHZhciBkZWZlcnJlZCA9IG5ldyBEZWZlcnJlZCgpO1xyXG5cdFx0dmFyIGlzSlNPTlAgPSB4aHJPcHRpb25zLmRhdGFUeXBlICYmIHhock9wdGlvbnMuZGF0YVR5cGUudG9Mb3dlckNhc2UoKSA9PT0gXCJqc29ucFwiXHJcblx0XHR2YXIgc2VyaWFsaXplID0geGhyT3B0aW9ucy5zZXJpYWxpemUgPSBpc0pTT05QID8gaWRlbnRpdHkgOiB4aHJPcHRpb25zLnNlcmlhbGl6ZSB8fCBKU09OLnN0cmluZ2lmeTtcclxuXHRcdHZhciBkZXNlcmlhbGl6ZSA9IHhock9wdGlvbnMuZGVzZXJpYWxpemUgPSBpc0pTT05QID8gaWRlbnRpdHkgOiB4aHJPcHRpb25zLmRlc2VyaWFsaXplIHx8IEpTT04ucGFyc2U7XHJcblx0XHR2YXIgZXh0cmFjdCA9IGlzSlNPTlAgPyBmdW5jdGlvbihqc29ucCkgeyByZXR1cm4ganNvbnAucmVzcG9uc2VUZXh0IH0gOiB4aHJPcHRpb25zLmV4dHJhY3QgfHwgZnVuY3Rpb24oeGhyKSB7XHJcblx0XHRcdGlmICh4aHIucmVzcG9uc2VUZXh0Lmxlbmd0aCA9PT0gMCAmJiBkZXNlcmlhbGl6ZSA9PT0gSlNPTi5wYXJzZSkge1xyXG5cdFx0XHRcdHJldHVybiBudWxsXHJcblx0XHRcdH0gZWxzZSB7XHJcblx0XHRcdFx0cmV0dXJuIHhoci5yZXNwb25zZVRleHRcclxuXHRcdFx0fVxyXG5cdFx0fTtcclxuXHRcdHhock9wdGlvbnMubWV0aG9kID0gKHhock9wdGlvbnMubWV0aG9kIHx8IFwiR0VUXCIpLnRvVXBwZXJDYXNlKCk7XHJcblx0XHR4aHJPcHRpb25zLnVybCA9IHBhcmFtZXRlcml6ZVVybCh4aHJPcHRpb25zLnVybCwgeGhyT3B0aW9ucy5kYXRhKTtcclxuXHRcdHhock9wdGlvbnMgPSBiaW5kRGF0YSh4aHJPcHRpb25zLCB4aHJPcHRpb25zLmRhdGEsIHNlcmlhbGl6ZSk7XHJcblx0XHR4aHJPcHRpb25zLm9ubG9hZCA9IHhock9wdGlvbnMub25lcnJvciA9IGZ1bmN0aW9uKGUpIHtcclxuXHRcdFx0dHJ5IHtcclxuXHRcdFx0XHRlID0gZSB8fCBldmVudDtcclxuXHRcdFx0XHR2YXIgdW53cmFwID0gKGUudHlwZSA9PT0gXCJsb2FkXCIgPyB4aHJPcHRpb25zLnVud3JhcFN1Y2Nlc3MgOiB4aHJPcHRpb25zLnVud3JhcEVycm9yKSB8fCBpZGVudGl0eTtcclxuXHRcdFx0XHR2YXIgcmVzcG9uc2UgPSB1bndyYXAoZGVzZXJpYWxpemUoZXh0cmFjdChlLnRhcmdldCwgeGhyT3B0aW9ucykpLCBlLnRhcmdldCk7XHJcblx0XHRcdFx0aWYgKGUudHlwZSA9PT0gXCJsb2FkXCIpIHtcclxuXHRcdFx0XHRcdGlmIChpc0FycmF5KHJlc3BvbnNlKSAmJiB4aHJPcHRpb25zLnR5cGUpIHtcclxuXHRcdFx0XHRcdFx0Zm9yRWFjaChyZXNwb25zZSwgZnVuY3Rpb24gKHJlcywgaSkge1xyXG5cdFx0XHRcdFx0XHRcdHJlc3BvbnNlW2ldID0gbmV3IHhock9wdGlvbnMudHlwZShyZXMpO1xyXG5cdFx0XHRcdFx0XHR9KTtcclxuXHRcdFx0XHRcdH0gZWxzZSBpZiAoeGhyT3B0aW9ucy50eXBlKSB7XHJcblx0XHRcdFx0XHRcdHJlc3BvbnNlID0gbmV3IHhock9wdGlvbnMudHlwZShyZXNwb25zZSk7XHJcblx0XHRcdFx0XHR9XHJcblx0XHRcdFx0fVxyXG5cclxuXHRcdFx0XHRkZWZlcnJlZFtlLnR5cGUgPT09IFwibG9hZFwiID8gXCJyZXNvbHZlXCIgOiBcInJlamVjdFwiXShyZXNwb25zZSk7XHJcblx0XHRcdH0gY2F0Y2ggKGUpIHtcclxuXHRcdFx0XHRtLmRlZmVycmVkLm9uZXJyb3IoZSk7XHJcblx0XHRcdFx0ZGVmZXJyZWQucmVqZWN0KGUpO1xyXG5cdFx0XHR9XHJcblxyXG5cdFx0XHRpZiAoeGhyT3B0aW9ucy5iYWNrZ3JvdW5kICE9PSB0cnVlKSBtLmVuZENvbXB1dGF0aW9uKClcclxuXHRcdH1cclxuXHJcblx0XHRhamF4KHhock9wdGlvbnMpO1xyXG5cdFx0ZGVmZXJyZWQucHJvbWlzZSA9IHByb3BpZnkoZGVmZXJyZWQucHJvbWlzZSwgeGhyT3B0aW9ucy5pbml0aWFsVmFsdWUpO1xyXG5cdFx0cmV0dXJuIGRlZmVycmVkLnByb21pc2U7XHJcblx0fTtcclxuXHJcblx0Ly90ZXN0aW5nIEFQSVxyXG5cdG0uZGVwcyA9IGZ1bmN0aW9uKG1vY2spIHtcclxuXHRcdGluaXRpYWxpemUod2luZG93ID0gbW9jayB8fCB3aW5kb3cpO1xyXG5cdFx0cmV0dXJuIHdpbmRvdztcclxuXHR9O1xyXG5cdC8vZm9yIGludGVybmFsIHRlc3Rpbmcgb25seSwgZG8gbm90IHVzZSBgbS5kZXBzLmZhY3RvcnlgXHJcblx0bS5kZXBzLmZhY3RvcnkgPSBhcHA7XHJcblxyXG5cdHJldHVybiBtO1xyXG59KSh0eXBlb2Ygd2luZG93ICE9PSBcInVuZGVmaW5lZFwiID8gd2luZG93IDoge30pO1xyXG5cclxuaWYgKHR5cGVvZiBtb2R1bGUgPT09IFwib2JqZWN0XCIgJiYgbW9kdWxlICE9IG51bGwgJiYgbW9kdWxlLmV4cG9ydHMpIG1vZHVsZS5leHBvcnRzID0gbTtcclxuZWxzZSBpZiAodHlwZW9mIGRlZmluZSA9PT0gXCJmdW5jdGlvblwiICYmIGRlZmluZS5hbWQpIGRlZmluZShmdW5jdGlvbigpIHsgcmV0dXJuIG0gfSk7XHJcbiIsInZhciB1dGlsID0gcmVxdWlyZSgnLi91dGlsJyk7XHJcblxyXG4vLyBodHRwczovL2dpc3QuZ2l0aHViLmNvbS9ncmUvMTY1MDI5NFxyXG52YXIgZWFzaW5nID0ge1xyXG4gIGVhc2VJbk91dEN1YmljOiBmdW5jdGlvbih0KSB7XHJcbiAgICByZXR1cm4gdCA8IDAuNSA/IDQgKiB0ICogdCAqIHQgOiAodCAtIDEpICogKDIgKiB0IC0gMikgKiAoMiAqIHQgLSAyKSArIDE7XHJcbiAgfSxcclxufTtcclxuXHJcbmZ1bmN0aW9uIG1ha2VQaWVjZShrLCBwaWVjZSwgaW52ZXJ0KSB7XHJcbiAgdmFyIGtleSA9IGludmVydCA/IHV0aWwuaW52ZXJ0S2V5KGspIDogaztcclxuICByZXR1cm4ge1xyXG4gICAga2V5OiBrZXksXHJcbiAgICBwb3M6IHV0aWwua2V5MnBvcyhrZXkpLFxyXG4gICAgcm9sZTogcGllY2Uucm9sZSxcclxuICAgIGNvbG9yOiBwaWVjZS5jb2xvclxyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHNhbWVQaWVjZShwMSwgcDIpIHtcclxuICByZXR1cm4gcDEucm9sZSA9PT0gcDIucm9sZSAmJiBwMS5jb2xvciA9PT0gcDIuY29sb3I7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGNsb3NlcihwaWVjZSwgcGllY2VzKSB7XHJcbiAgcmV0dXJuIHBpZWNlcy5zb3J0KGZ1bmN0aW9uKHAxLCBwMikge1xyXG4gICAgcmV0dXJuIHV0aWwuZGlzdGFuY2UocGllY2UucG9zLCBwMS5wb3MpIC0gdXRpbC5kaXN0YW5jZShwaWVjZS5wb3MsIHAyLnBvcyk7XHJcbiAgfSlbMF07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGNvbXB1dGVQbGFuKHByZXYsIGN1cnJlbnQpIHtcclxuICB2YXIgYm91bmRzID0gY3VycmVudC5ib3VuZHMoKSxcclxuICAgIHdpZHRoID0gYm91bmRzLndpZHRoIC8gOCxcclxuICAgIGhlaWdodCA9IGJvdW5kcy5oZWlnaHQgLyA4LFxyXG4gICAgYW5pbXMgPSB7fSxcclxuICAgIGFuaW1lZE9yaWdzID0gW10sXHJcbiAgICBmYWRpbmdzID0gW10sXHJcbiAgICBtaXNzaW5ncyA9IFtdLFxyXG4gICAgbmV3cyA9IFtdLFxyXG4gICAgaW52ZXJ0ID0gcHJldi5vcmllbnRhdGlvbiAhPT0gY3VycmVudC5vcmllbnRhdGlvbixcclxuICAgIHByZVBpZWNlcyA9IHt9LFxyXG4gICAgd2hpdGUgPSBjdXJyZW50Lm9yaWVudGF0aW9uID09PSAnd2hpdGUnO1xyXG4gIGZvciAodmFyIHBrIGluIHByZXYucGllY2VzKSB7XHJcbiAgICB2YXIgcGllY2UgPSBtYWtlUGllY2UocGssIHByZXYucGllY2VzW3BrXSwgaW52ZXJ0KTtcclxuICAgIHByZVBpZWNlc1twaWVjZS5rZXldID0gcGllY2U7XHJcbiAgfVxyXG4gIGZvciAodmFyIGkgPSAwOyBpIDwgdXRpbC5hbGxLZXlzLmxlbmd0aDsgaSsrKSB7XHJcbiAgICB2YXIga2V5ID0gdXRpbC5hbGxLZXlzW2ldO1xyXG4gICAgaWYgKGtleSAhPT0gY3VycmVudC5tb3ZhYmxlLmRyb3BwZWRbMV0pIHtcclxuICAgICAgdmFyIGN1clAgPSBjdXJyZW50LnBpZWNlc1trZXldO1xyXG4gICAgICB2YXIgcHJlUCA9IHByZVBpZWNlc1trZXldO1xyXG4gICAgICBpZiAoY3VyUCkge1xyXG4gICAgICAgIGlmIChwcmVQKSB7XHJcbiAgICAgICAgICBpZiAoIXNhbWVQaWVjZShjdXJQLCBwcmVQKSkge1xyXG4gICAgICAgICAgICBtaXNzaW5ncy5wdXNoKHByZVApO1xyXG4gICAgICAgICAgICBuZXdzLnB1c2gobWFrZVBpZWNlKGtleSwgY3VyUCwgZmFsc2UpKTtcclxuICAgICAgICAgIH1cclxuICAgICAgICB9IGVsc2VcclxuICAgICAgICAgIG5ld3MucHVzaChtYWtlUGllY2Uoa2V5LCBjdXJQLCBmYWxzZSkpO1xyXG4gICAgICB9IGVsc2UgaWYgKHByZVApXHJcbiAgICAgICAgbWlzc2luZ3MucHVzaChwcmVQKTtcclxuICAgIH1cclxuICB9XHJcbiAgbmV3cy5mb3JFYWNoKGZ1bmN0aW9uKG5ld1ApIHtcclxuICAgIHZhciBwcmVQID0gY2xvc2VyKG5ld1AsIG1pc3NpbmdzLmZpbHRlcih1dGlsLnBhcnRpYWwoc2FtZVBpZWNlLCBuZXdQKSkpO1xyXG4gICAgaWYgKHByZVApIHtcclxuICAgICAgdmFyIG9yaWcgPSB3aGl0ZSA/IHByZVAucG9zIDogbmV3UC5wb3M7XHJcbiAgICAgIHZhciBkZXN0ID0gd2hpdGUgPyBuZXdQLnBvcyA6IHByZVAucG9zO1xyXG4gICAgICB2YXIgdmVjdG9yID0gWyhvcmlnWzBdIC0gZGVzdFswXSkgKiB3aWR0aCwgKGRlc3RbMV0gLSBvcmlnWzFdKSAqIGhlaWdodF07XHJcbiAgICAgIGFuaW1zW25ld1Aua2V5XSA9IFt2ZWN0b3IsIHZlY3Rvcl07XHJcbiAgICAgIGFuaW1lZE9yaWdzLnB1c2gocHJlUC5rZXkpO1xyXG4gICAgfVxyXG4gIH0pO1xyXG4gIG1pc3NpbmdzLmZvckVhY2goZnVuY3Rpb24ocCkge1xyXG4gICAgaWYgKFxyXG4gICAgICBwLmtleSAhPT0gY3VycmVudC5tb3ZhYmxlLmRyb3BwZWRbMF0gJiZcclxuICAgICAgIXV0aWwuY29udGFpbnNYKGFuaW1lZE9yaWdzLCBwLmtleSkgJiZcclxuICAgICAgIShjdXJyZW50Lml0ZW1zID8gY3VycmVudC5pdGVtcy5yZW5kZXIocC5wb3MsIHAua2V5KSA6IGZhbHNlKVxyXG4gICAgKVxyXG4gICAgICBmYWRpbmdzLnB1c2goe1xyXG4gICAgICAgIHBpZWNlOiBwLFxyXG4gICAgICAgIG9wYWNpdHk6IDFcclxuICAgICAgfSk7XHJcbiAgfSk7XHJcblxyXG4gIHJldHVybiB7XHJcbiAgICBhbmltczogYW5pbXMsXHJcbiAgICBmYWRpbmdzOiBmYWRpbmdzXHJcbiAgfTtcclxufVxyXG5cclxuZnVuY3Rpb24gcm91bmRCeShuLCBieSkge1xyXG4gIHJldHVybiBNYXRoLnJvdW5kKG4gKiBieSkgLyBieTtcclxufVxyXG5cclxuZnVuY3Rpb24gZ28oZGF0YSkge1xyXG4gIGlmICghZGF0YS5hbmltYXRpb24uY3VycmVudC5zdGFydCkgcmV0dXJuOyAvLyBhbmltYXRpb24gd2FzIGNhbmNlbGVkXHJcbiAgdmFyIHJlc3QgPSAxIC0gKG5ldyBEYXRlKCkuZ2V0VGltZSgpIC0gZGF0YS5hbmltYXRpb24uY3VycmVudC5zdGFydCkgLyBkYXRhLmFuaW1hdGlvbi5jdXJyZW50LmR1cmF0aW9uO1xyXG4gIGlmIChyZXN0IDw9IDApIHtcclxuICAgIGRhdGEuYW5pbWF0aW9uLmN1cnJlbnQgPSB7fTtcclxuICAgIGRhdGEucmVuZGVyKCk7XHJcbiAgfSBlbHNlIHtcclxuICAgIHZhciBlYXNlID0gZWFzaW5nLmVhc2VJbk91dEN1YmljKHJlc3QpO1xyXG4gICAgZm9yICh2YXIga2V5IGluIGRhdGEuYW5pbWF0aW9uLmN1cnJlbnQuYW5pbXMpIHtcclxuICAgICAgdmFyIGNmZyA9IGRhdGEuYW5pbWF0aW9uLmN1cnJlbnQuYW5pbXNba2V5XTtcclxuICAgICAgY2ZnWzFdID0gW3JvdW5kQnkoY2ZnWzBdWzBdICogZWFzZSwgMTApLCByb3VuZEJ5KGNmZ1swXVsxXSAqIGVhc2UsIDEwKV07XHJcbiAgICB9XHJcbiAgICBmb3IgKHZhciBpIGluIGRhdGEuYW5pbWF0aW9uLmN1cnJlbnQuZmFkaW5ncykge1xyXG4gICAgICBkYXRhLmFuaW1hdGlvbi5jdXJyZW50LmZhZGluZ3NbaV0ub3BhY2l0eSA9IHJvdW5kQnkoZWFzZSwgMTAwKTtcclxuICAgIH1cclxuICAgIGRhdGEucmVuZGVyKCk7XHJcbiAgICB1dGlsLnJlcXVlc3RBbmltYXRpb25GcmFtZShmdW5jdGlvbigpIHtcclxuICAgICAgZ28oZGF0YSk7XHJcbiAgICB9KTtcclxuICB9XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGFuaW1hdGUodHJhbnNmb3JtYXRpb24sIGRhdGEpIHtcclxuICAvLyBjbG9uZSBkYXRhXHJcbiAgdmFyIHByZXYgPSB7XHJcbiAgICBvcmllbnRhdGlvbjogZGF0YS5vcmllbnRhdGlvbixcclxuICAgIHBpZWNlczoge31cclxuICB9O1xyXG4gIC8vIGNsb25lIHBpZWNlc1xyXG4gIGZvciAodmFyIGtleSBpbiBkYXRhLnBpZWNlcykge1xyXG4gICAgcHJldi5waWVjZXNba2V5XSA9IHtcclxuICAgICAgcm9sZTogZGF0YS5waWVjZXNba2V5XS5yb2xlLFxyXG4gICAgICBjb2xvcjogZGF0YS5waWVjZXNba2V5XS5jb2xvclxyXG4gICAgfTtcclxuICB9XHJcbiAgdmFyIHJlc3VsdCA9IHRyYW5zZm9ybWF0aW9uKCk7XHJcbiAgaWYgKGRhdGEuYW5pbWF0aW9uLmVuYWJsZWQpIHtcclxuICAgIHZhciBwbGFuID0gY29tcHV0ZVBsYW4ocHJldiwgZGF0YSk7XHJcbiAgICBpZiAoT2JqZWN0LmtleXMocGxhbi5hbmltcykubGVuZ3RoID4gMCB8fCBwbGFuLmZhZGluZ3MubGVuZ3RoID4gMCkge1xyXG4gICAgICB2YXIgYWxyZWFkeVJ1bm5pbmcgPSBkYXRhLmFuaW1hdGlvbi5jdXJyZW50LnN0YXJ0O1xyXG4gICAgICBkYXRhLmFuaW1hdGlvbi5jdXJyZW50ID0ge1xyXG4gICAgICAgIHN0YXJ0OiBuZXcgRGF0ZSgpLmdldFRpbWUoKSxcclxuICAgICAgICBkdXJhdGlvbjogZGF0YS5hbmltYXRpb24uZHVyYXRpb24sXHJcbiAgICAgICAgYW5pbXM6IHBsYW4uYW5pbXMsXHJcbiAgICAgICAgZmFkaW5nczogcGxhbi5mYWRpbmdzXHJcbiAgICAgIH07XHJcbiAgICAgIGlmICghYWxyZWFkeVJ1bm5pbmcpIGdvKGRhdGEpO1xyXG4gICAgfSBlbHNlIHtcclxuICAgICAgLy8gZG9uJ3QgYW5pbWF0ZSwganVzdCByZW5kZXIgcmlnaHQgYXdheVxyXG4gICAgICBkYXRhLnJlbmRlclJBRigpO1xyXG4gICAgfVxyXG4gIH0gZWxzZSB7XHJcbiAgICAvLyBhbmltYXRpb25zIGFyZSBub3cgZGlzYWJsZWRcclxuICAgIGRhdGEucmVuZGVyUkFGKCk7XHJcbiAgfVxyXG4gIHJldHVybiByZXN1bHQ7XHJcbn1cclxuXHJcbi8vIHRyYW5zZm9ybWF0aW9uIGlzIGEgZnVuY3Rpb25cclxuLy8gYWNjZXB0cyBib2FyZCBkYXRhIGFuZCBhbnkgbnVtYmVyIG9mIGFyZ3VtZW50cyxcclxuLy8gYW5kIG11dGF0ZXMgdGhlIGJvYXJkLlxyXG5tb2R1bGUuZXhwb3J0cyA9IGZ1bmN0aW9uKHRyYW5zZm9ybWF0aW9uLCBkYXRhLCBza2lwKSB7XHJcbiAgcmV0dXJuIGZ1bmN0aW9uKCkge1xyXG4gICAgdmFyIHRyYW5zZm9ybWF0aW9uQXJncyA9IFtkYXRhXS5jb25jYXQoQXJyYXkucHJvdG90eXBlLnNsaWNlLmNhbGwoYXJndW1lbnRzLCAwKSk7XHJcbiAgICBpZiAoIWRhdGEucmVuZGVyKSByZXR1cm4gdHJhbnNmb3JtYXRpb24uYXBwbHkobnVsbCwgdHJhbnNmb3JtYXRpb25BcmdzKTtcclxuICAgIGVsc2UgaWYgKGRhdGEuYW5pbWF0aW9uLmVuYWJsZWQgJiYgIXNraXApXHJcbiAgICAgIHJldHVybiBhbmltYXRlKHV0aWwucGFydGlhbEFwcGx5KHRyYW5zZm9ybWF0aW9uLCB0cmFuc2Zvcm1hdGlvbkFyZ3MpLCBkYXRhKTtcclxuICAgIGVsc2Uge1xyXG4gICAgICB2YXIgcmVzdWx0ID0gdHJhbnNmb3JtYXRpb24uYXBwbHkobnVsbCwgdHJhbnNmb3JtYXRpb25BcmdzKTtcclxuICAgICAgZGF0YS5yZW5kZXJSQUYoKTtcclxuICAgICAgcmV0dXJuIHJlc3VsdDtcclxuICAgIH1cclxuICB9O1xyXG59O1xyXG4iLCJ2YXIgYm9hcmQgPSByZXF1aXJlKCcuL2JvYXJkJyk7XHJcblxyXG5tb2R1bGUuZXhwb3J0cyA9IGZ1bmN0aW9uKGNvbnRyb2xsZXIpIHtcclxuXHJcbiAgcmV0dXJuIHtcclxuICAgIHNldDogY29udHJvbGxlci5zZXQsXHJcbiAgICB0b2dnbGVPcmllbnRhdGlvbjogY29udHJvbGxlci50b2dnbGVPcmllbnRhdGlvbixcclxuICAgIGdldE9yaWVudGF0aW9uOiBjb250cm9sbGVyLmdldE9yaWVudGF0aW9uLFxyXG4gICAgZ2V0UGllY2VzOiBmdW5jdGlvbigpIHtcclxuICAgICAgcmV0dXJuIGNvbnRyb2xsZXIuZGF0YS5waWVjZXM7XHJcbiAgICB9LFxyXG4gICAgZ2V0TWF0ZXJpYWxEaWZmOiBmdW5jdGlvbigpIHtcclxuICAgICAgcmV0dXJuIGJvYXJkLmdldE1hdGVyaWFsRGlmZihjb250cm9sbGVyLmRhdGEpO1xyXG4gICAgfSxcclxuICAgIGdldEZlbjogY29udHJvbGxlci5nZXRGZW4sXHJcbiAgICBtb3ZlOiBjb250cm9sbGVyLmFwaU1vdmUsXHJcbiAgICBuZXdQaWVjZTogY29udHJvbGxlci5hcGlOZXdQaWVjZSxcclxuICAgIHNldFBpZWNlczogY29udHJvbGxlci5zZXRQaWVjZXMsXHJcbiAgICBzZXRDaGVjazogY29udHJvbGxlci5zZXRDaGVjayxcclxuICAgIHBsYXlQcmVtb3ZlOiBjb250cm9sbGVyLnBsYXlQcmVtb3ZlLFxyXG4gICAgcGxheVByZWRyb3A6IGNvbnRyb2xsZXIucGxheVByZWRyb3AsXHJcbiAgICBjYW5jZWxQcmVtb3ZlOiBjb250cm9sbGVyLmNhbmNlbFByZW1vdmUsXHJcbiAgICBjYW5jZWxQcmVkcm9wOiBjb250cm9sbGVyLmNhbmNlbFByZWRyb3AsXHJcbiAgICBjYW5jZWxNb3ZlOiBjb250cm9sbGVyLmNhbmNlbE1vdmUsXHJcbiAgICBzdG9wOiBjb250cm9sbGVyLnN0b3AsXHJcbiAgICBleHBsb2RlOiBjb250cm9sbGVyLmV4cGxvZGUsXHJcbiAgICBzZXRBdXRvU2hhcGVzOiBjb250cm9sbGVyLnNldEF1dG9TaGFwZXMsXHJcbiAgICBzZXRTaGFwZXM6IGNvbnRyb2xsZXIuc2V0U2hhcGVzLFxyXG4gICAgZGF0YTogY29udHJvbGxlci5kYXRhIC8vIGRpcmVjdGx5IGV4cG9zZXMgY2hlc3Nncm91bmQgc3RhdGUgZm9yIG1vcmUgbWVzc2luZyBhcm91bmRcclxuICB9O1xyXG59O1xyXG4iLCJ2YXIgdXRpbCA9IHJlcXVpcmUoJy4vdXRpbCcpO1xyXG52YXIgcHJlbW92ZSA9IHJlcXVpcmUoJy4vcHJlbW92ZScpO1xyXG52YXIgYW5pbSA9IHJlcXVpcmUoJy4vYW5pbScpO1xyXG52YXIgaG9sZCA9IHJlcXVpcmUoJy4vaG9sZCcpO1xyXG5cclxuZnVuY3Rpb24gY2FsbFVzZXJGdW5jdGlvbihmKSB7XHJcbiAgc2V0VGltZW91dChmLCAxKTtcclxufVxyXG5cclxuZnVuY3Rpb24gdG9nZ2xlT3JpZW50YXRpb24oZGF0YSkge1xyXG4gIGRhdGEub3JpZW50YXRpb24gPSB1dGlsLm9wcG9zaXRlKGRhdGEub3JpZW50YXRpb24pO1xyXG59XHJcblxyXG5mdW5jdGlvbiByZXNldChkYXRhKSB7XHJcbiAgZGF0YS5sYXN0TW92ZSA9IG51bGw7XHJcbiAgc2V0U2VsZWN0ZWQoZGF0YSwgbnVsbCk7XHJcbiAgdW5zZXRQcmVtb3ZlKGRhdGEpO1xyXG4gIHVuc2V0UHJlZHJvcChkYXRhKTtcclxufVxyXG5cclxuZnVuY3Rpb24gc2V0UGllY2VzKGRhdGEsIHBpZWNlcykge1xyXG4gIE9iamVjdC5rZXlzKHBpZWNlcykuZm9yRWFjaChmdW5jdGlvbihrZXkpIHtcclxuICAgIGlmIChwaWVjZXNba2V5XSkgZGF0YS5waWVjZXNba2V5XSA9IHBpZWNlc1trZXldO1xyXG4gICAgZWxzZSBkZWxldGUgZGF0YS5waWVjZXNba2V5XTtcclxuICB9KTtcclxuICBkYXRhLm1vdmFibGUuZHJvcHBlZCA9IFtdO1xyXG59XHJcblxyXG5mdW5jdGlvbiBzZXRDaGVjayhkYXRhLCBjb2xvcikge1xyXG4gIHZhciBjaGVja0NvbG9yID0gY29sb3IgfHwgZGF0YS50dXJuQ29sb3I7XHJcbiAgT2JqZWN0LmtleXMoZGF0YS5waWVjZXMpLmZvckVhY2goZnVuY3Rpb24oa2V5KSB7XHJcbiAgICBpZiAoZGF0YS5waWVjZXNba2V5XS5jb2xvciA9PT0gY2hlY2tDb2xvciAmJiBkYXRhLnBpZWNlc1trZXldLnJvbGUgPT09ICdraW5nJykgZGF0YS5jaGVjayA9IGtleTtcclxuICB9KTtcclxufVxyXG5cclxuZnVuY3Rpb24gc2V0UHJlbW92ZShkYXRhLCBvcmlnLCBkZXN0KSB7XHJcbiAgdW5zZXRQcmVkcm9wKGRhdGEpO1xyXG4gIGRhdGEucHJlbW92YWJsZS5jdXJyZW50ID0gW29yaWcsIGRlc3RdO1xyXG4gIGNhbGxVc2VyRnVuY3Rpb24odXRpbC5wYXJ0aWFsKGRhdGEucHJlbW92YWJsZS5ldmVudHMuc2V0LCBvcmlnLCBkZXN0KSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHVuc2V0UHJlbW92ZShkYXRhKSB7XHJcbiAgaWYgKGRhdGEucHJlbW92YWJsZS5jdXJyZW50KSB7XHJcbiAgICBkYXRhLnByZW1vdmFibGUuY3VycmVudCA9IG51bGw7XHJcbiAgICBjYWxsVXNlckZ1bmN0aW9uKGRhdGEucHJlbW92YWJsZS5ldmVudHMudW5zZXQpO1xyXG4gIH1cclxufVxyXG5cclxuZnVuY3Rpb24gc2V0UHJlZHJvcChkYXRhLCByb2xlLCBrZXkpIHtcclxuICB1bnNldFByZW1vdmUoZGF0YSk7XHJcbiAgZGF0YS5wcmVkcm9wcGFibGUuY3VycmVudCA9IHtcclxuICAgIHJvbGU6IHJvbGUsXHJcbiAgICBrZXk6IGtleVxyXG4gIH07XHJcbiAgY2FsbFVzZXJGdW5jdGlvbih1dGlsLnBhcnRpYWwoZGF0YS5wcmVkcm9wcGFibGUuZXZlbnRzLnNldCwgcm9sZSwga2V5KSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHVuc2V0UHJlZHJvcChkYXRhKSB7XHJcbiAgaWYgKGRhdGEucHJlZHJvcHBhYmxlLmN1cnJlbnQua2V5KSB7XHJcbiAgICBkYXRhLnByZWRyb3BwYWJsZS5jdXJyZW50ID0ge307XHJcbiAgICBjYWxsVXNlckZ1bmN0aW9uKGRhdGEucHJlZHJvcHBhYmxlLmV2ZW50cy51bnNldCk7XHJcbiAgfVxyXG59XHJcblxyXG5mdW5jdGlvbiB0cnlBdXRvQ2FzdGxlKGRhdGEsIG9yaWcsIGRlc3QpIHtcclxuICBpZiAoIWRhdGEuYXV0b0Nhc3RsZSkgcmV0dXJuO1xyXG4gIHZhciBraW5nID0gZGF0YS5waWVjZXNbZGVzdF07XHJcbiAgaWYgKGtpbmcucm9sZSAhPT0gJ2tpbmcnKSByZXR1cm47XHJcbiAgdmFyIG9yaWdQb3MgPSB1dGlsLmtleTJwb3Mob3JpZyk7XHJcbiAgaWYgKG9yaWdQb3NbMF0gIT09IDUpIHJldHVybjtcclxuICBpZiAob3JpZ1Bvc1sxXSAhPT0gMSAmJiBvcmlnUG9zWzFdICE9PSA4KSByZXR1cm47XHJcbiAgdmFyIGRlc3RQb3MgPSB1dGlsLmtleTJwb3MoZGVzdCksXHJcbiAgICBvbGRSb29rUG9zLCBuZXdSb29rUG9zLCBuZXdLaW5nUG9zO1xyXG4gIGlmIChkZXN0UG9zWzBdID09PSA3IHx8IGRlc3RQb3NbMF0gPT09IDgpIHtcclxuICAgIG9sZFJvb2tQb3MgPSB1dGlsLnBvczJrZXkoWzgsIG9yaWdQb3NbMV1dKTtcclxuICAgIG5ld1Jvb2tQb3MgPSB1dGlsLnBvczJrZXkoWzYsIG9yaWdQb3NbMV1dKTtcclxuICAgIG5ld0tpbmdQb3MgPSB1dGlsLnBvczJrZXkoWzcsIG9yaWdQb3NbMV1dKTtcclxuICB9IGVsc2UgaWYgKGRlc3RQb3NbMF0gPT09IDMgfHwgZGVzdFBvc1swXSA9PT0gMSkge1xyXG4gICAgb2xkUm9va1BvcyA9IHV0aWwucG9zMmtleShbMSwgb3JpZ1Bvc1sxXV0pO1xyXG4gICAgbmV3Um9va1BvcyA9IHV0aWwucG9zMmtleShbNCwgb3JpZ1Bvc1sxXV0pO1xyXG4gICAgbmV3S2luZ1BvcyA9IHV0aWwucG9zMmtleShbMywgb3JpZ1Bvc1sxXV0pO1xyXG4gIH0gZWxzZSByZXR1cm47XHJcbiAgZGVsZXRlIGRhdGEucGllY2VzW29yaWddO1xyXG4gIGRlbGV0ZSBkYXRhLnBpZWNlc1tkZXN0XTtcclxuICBkZWxldGUgZGF0YS5waWVjZXNbb2xkUm9va1Bvc107XHJcbiAgZGF0YS5waWVjZXNbbmV3S2luZ1Bvc10gPSB7XHJcbiAgICByb2xlOiAna2luZycsXHJcbiAgICBjb2xvcjoga2luZy5jb2xvclxyXG4gIH07XHJcbiAgZGF0YS5waWVjZXNbbmV3Um9va1Bvc10gPSB7XHJcbiAgICByb2xlOiAncm9vaycsXHJcbiAgICBjb2xvcjoga2luZy5jb2xvclxyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGJhc2VNb3ZlKGRhdGEsIG9yaWcsIGRlc3QpIHtcclxuICB2YXIgc3VjY2VzcyA9IGFuaW0oZnVuY3Rpb24oKSB7XHJcbiAgICBpZiAob3JpZyA9PT0gZGVzdCB8fCAhZGF0YS5waWVjZXNbb3JpZ10pIHJldHVybiBmYWxzZTtcclxuICAgIHZhciBjYXB0dXJlZCA9IChcclxuICAgICAgZGF0YS5waWVjZXNbZGVzdF0gJiZcclxuICAgICAgZGF0YS5waWVjZXNbZGVzdF0uY29sb3IgIT09IGRhdGEucGllY2VzW29yaWddLmNvbG9yXHJcbiAgICApID8gZGF0YS5waWVjZXNbZGVzdF0gOiBudWxsO1xyXG4gICAgY2FsbFVzZXJGdW5jdGlvbih1dGlsLnBhcnRpYWwoZGF0YS5ldmVudHMubW92ZSwgb3JpZywgZGVzdCwgY2FwdHVyZWQpKTtcclxuICAgIGRhdGEucGllY2VzW2Rlc3RdID0gZGF0YS5waWVjZXNbb3JpZ107XHJcbiAgICBkZWxldGUgZGF0YS5waWVjZXNbb3JpZ107XHJcbiAgICBkYXRhLmxhc3RNb3ZlID0gW29yaWcsIGRlc3RdO1xyXG4gICAgZGF0YS5jaGVjayA9IG51bGw7XHJcbiAgICB0cnlBdXRvQ2FzdGxlKGRhdGEsIG9yaWcsIGRlc3QpO1xyXG4gICAgY2FsbFVzZXJGdW5jdGlvbihkYXRhLmV2ZW50cy5jaGFuZ2UpO1xyXG4gICAgcmV0dXJuIHRydWU7XHJcbiAgfSwgZGF0YSkoKTtcclxuICBpZiAoc3VjY2VzcykgZGF0YS5tb3ZhYmxlLmRyb3BwZWQgPSBbXTtcclxuICByZXR1cm4gc3VjY2VzcztcclxufVxyXG5cclxuZnVuY3Rpb24gYmFzZU5ld1BpZWNlKGRhdGEsIHBpZWNlLCBrZXkpIHtcclxuICBpZiAoZGF0YS5waWVjZXNba2V5XSkgcmV0dXJuIGZhbHNlO1xyXG4gIGNhbGxVc2VyRnVuY3Rpb24odXRpbC5wYXJ0aWFsKGRhdGEuZXZlbnRzLmRyb3BOZXdQaWVjZSwgcGllY2UsIGtleSkpO1xyXG4gIGRhdGEucGllY2VzW2tleV0gPSBwaWVjZTtcclxuICBkYXRhLmxhc3RNb3ZlID0gW2tleSwga2V5XTtcclxuICBkYXRhLmNoZWNrID0gbnVsbDtcclxuICBjYWxsVXNlckZ1bmN0aW9uKGRhdGEuZXZlbnRzLmNoYW5nZSk7XHJcbiAgZGF0YS5tb3ZhYmxlLmRyb3BwZWQgPSBbXTtcclxuICBkYXRhLm1vdmFibGUuZGVzdHMgPSB7fTtcclxuICBkYXRhLnR1cm5Db2xvciA9IHV0aWwub3Bwb3NpdGUoZGF0YS50dXJuQ29sb3IpO1xyXG4gIGRhdGEucmVuZGVyUkFGKCk7XHJcbiAgcmV0dXJuIHRydWU7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGJhc2VVc2VyTW92ZShkYXRhLCBvcmlnLCBkZXN0KSB7XHJcbiAgdmFyIHJlc3VsdCA9IGJhc2VNb3ZlKGRhdGEsIG9yaWcsIGRlc3QpO1xyXG4gIGlmIChyZXN1bHQpIHtcclxuICAgIGRhdGEubW92YWJsZS5kZXN0cyA9IHt9O1xyXG4gICAgZGF0YS50dXJuQ29sb3IgPSB1dGlsLm9wcG9zaXRlKGRhdGEudHVybkNvbG9yKTtcclxuICB9XHJcbiAgcmV0dXJuIHJlc3VsdDtcclxufVxyXG5cclxuZnVuY3Rpb24gYXBpTW92ZShkYXRhLCBvcmlnLCBkZXN0KSB7XHJcbiAgcmV0dXJuIGJhc2VNb3ZlKGRhdGEsIG9yaWcsIGRlc3QpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBhcGlOZXdQaWVjZShkYXRhLCBwaWVjZSwga2V5KSB7XHJcbiAgcmV0dXJuIGJhc2VOZXdQaWVjZShkYXRhLCBwaWVjZSwga2V5KTtcclxufVxyXG5cclxuZnVuY3Rpb24gdXNlck1vdmUoZGF0YSwgb3JpZywgZGVzdCkge1xyXG4gIGlmICghZGVzdCkge1xyXG4gICAgaG9sZC5jYW5jZWwoKTtcclxuICAgIHNldFNlbGVjdGVkKGRhdGEsIG51bGwpO1xyXG4gICAgaWYgKGRhdGEubW92YWJsZS5kcm9wT2ZmID09PSAndHJhc2gnKSB7XHJcbiAgICAgIGRlbGV0ZSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICAgICAgY2FsbFVzZXJGdW5jdGlvbihkYXRhLmV2ZW50cy5jaGFuZ2UpO1xyXG4gICAgfVxyXG4gIH0gZWxzZSBpZiAoY2FuTW92ZShkYXRhLCBvcmlnLCBkZXN0KSkge1xyXG4gICAgaWYgKGJhc2VVc2VyTW92ZShkYXRhLCBvcmlnLCBkZXN0KSkge1xyXG4gICAgICB2YXIgaG9sZFRpbWUgPSBob2xkLnN0b3AoKTtcclxuICAgICAgc2V0U2VsZWN0ZWQoZGF0YSwgbnVsbCk7XHJcbiAgICAgIGNhbGxVc2VyRnVuY3Rpb24odXRpbC5wYXJ0aWFsKGRhdGEubW92YWJsZS5ldmVudHMuYWZ0ZXIsIG9yaWcsIGRlc3QsIHtcclxuICAgICAgICBwcmVtb3ZlOiBmYWxzZSxcclxuICAgICAgICBob2xkVGltZTogaG9sZFRpbWVcclxuICAgICAgfSkpO1xyXG4gICAgICByZXR1cm4gdHJ1ZTtcclxuICAgIH1cclxuICB9IGVsc2UgaWYgKGNhblByZW1vdmUoZGF0YSwgb3JpZywgZGVzdCkpIHtcclxuICAgIHNldFByZW1vdmUoZGF0YSwgb3JpZywgZGVzdCk7XHJcbiAgICBzZXRTZWxlY3RlZChkYXRhLCBudWxsKTtcclxuICB9IGVsc2UgaWYgKGlzTW92YWJsZShkYXRhLCBkZXN0KSB8fCBpc1ByZW1vdmFibGUoZGF0YSwgZGVzdCkpIHtcclxuICAgIHNldFNlbGVjdGVkKGRhdGEsIGRlc3QpO1xyXG4gICAgaG9sZC5zdGFydCgpO1xyXG4gIH0gZWxzZSBzZXRTZWxlY3RlZChkYXRhLCBudWxsKTtcclxufVxyXG5cclxuZnVuY3Rpb24gZHJvcE5ld1BpZWNlKGRhdGEsIG9yaWcsIGRlc3QpIHtcclxuICBpZiAoY2FuRHJvcChkYXRhLCBvcmlnLCBkZXN0KSkge1xyXG4gICAgdmFyIHBpZWNlID0gZGF0YS5waWVjZXNbb3JpZ107XHJcbiAgICBkZWxldGUgZGF0YS5waWVjZXNbb3JpZ107XHJcbiAgICBiYXNlTmV3UGllY2UoZGF0YSwgcGllY2UsIGRlc3QpO1xyXG4gICAgZGF0YS5tb3ZhYmxlLmRyb3BwZWQgPSBbXTtcclxuICAgIGNhbGxVc2VyRnVuY3Rpb24odXRpbC5wYXJ0aWFsKGRhdGEubW92YWJsZS5ldmVudHMuYWZ0ZXJOZXdQaWVjZSwgcGllY2Uucm9sZSwgZGVzdCwge1xyXG4gICAgICBwcmVkcm9wOiBmYWxzZVxyXG4gICAgfSkpO1xyXG4gIH0gZWxzZSBpZiAoY2FuUHJlZHJvcChkYXRhLCBvcmlnLCBkZXN0KSkge1xyXG4gICAgc2V0UHJlZHJvcChkYXRhLCBkYXRhLnBpZWNlc1tvcmlnXS5yb2xlLCBkZXN0KTtcclxuICB9IGVsc2Uge1xyXG4gICAgdW5zZXRQcmVtb3ZlKGRhdGEpO1xyXG4gICAgdW5zZXRQcmVkcm9wKGRhdGEpO1xyXG4gIH1cclxuICBkZWxldGUgZGF0YS5waWVjZXNbb3JpZ107XHJcbiAgc2V0U2VsZWN0ZWQoZGF0YSwgbnVsbCk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHNlbGVjdFNxdWFyZShkYXRhLCBrZXkpIHtcclxuICBpZiAoZGF0YS5zZWxlY3RlZCkge1xyXG4gICAgaWYgKGtleSkge1xyXG4gICAgICBpZiAoZGF0YS5zZWxlY3RhYmxlLmVuYWJsZWQgJiYgZGF0YS5zZWxlY3RlZCAhPT0ga2V5KSB7XHJcbiAgICAgICAgaWYgKHVzZXJNb3ZlKGRhdGEsIGRhdGEuc2VsZWN0ZWQsIGtleSkpIGRhdGEuc3RhdHMuZHJhZ2dlZCA9IGZhbHNlO1xyXG4gICAgICB9IGVsc2UgaG9sZC5zdGFydCgpO1xyXG4gICAgfSBlbHNlIHtcclxuICAgICAgc2V0U2VsZWN0ZWQoZGF0YSwgbnVsbCk7XHJcbiAgICAgIGhvbGQuY2FuY2VsKCk7XHJcbiAgICB9XHJcbiAgfSBlbHNlIGlmIChpc01vdmFibGUoZGF0YSwga2V5KSB8fCBpc1ByZW1vdmFibGUoZGF0YSwga2V5KSkge1xyXG4gICAgc2V0U2VsZWN0ZWQoZGF0YSwga2V5KTtcclxuICAgIGhvbGQuc3RhcnQoKTtcclxuICB9XHJcbiAgaWYgKGtleSkgY2FsbFVzZXJGdW5jdGlvbih1dGlsLnBhcnRpYWwoZGF0YS5ldmVudHMuc2VsZWN0LCBrZXkpKTtcclxufVxyXG5cclxuZnVuY3Rpb24gc2V0U2VsZWN0ZWQoZGF0YSwga2V5KSB7XHJcbiAgZGF0YS5zZWxlY3RlZCA9IGtleTtcclxuICBpZiAoa2V5ICYmIGlzUHJlbW92YWJsZShkYXRhLCBrZXkpKVxyXG4gICAgZGF0YS5wcmVtb3ZhYmxlLmRlc3RzID0gcHJlbW92ZShkYXRhLnBpZWNlcywga2V5LCBkYXRhLnByZW1vdmFibGUuY2FzdGxlKTtcclxuICBlbHNlXHJcbiAgICBkYXRhLnByZW1vdmFibGUuZGVzdHMgPSBudWxsO1xyXG59XHJcblxyXG5mdW5jdGlvbiBpc01vdmFibGUoZGF0YSwgb3JpZykge1xyXG4gIHZhciBwaWVjZSA9IGRhdGEucGllY2VzW29yaWddO1xyXG4gIHJldHVybiBwaWVjZSAmJiAoXHJcbiAgICBkYXRhLm1vdmFibGUuY29sb3IgPT09ICdib3RoJyB8fCAoXHJcbiAgICAgIGRhdGEubW92YWJsZS5jb2xvciA9PT0gcGllY2UuY29sb3IgJiZcclxuICAgICAgZGF0YS50dXJuQ29sb3IgPT09IHBpZWNlLmNvbG9yXHJcbiAgICApKTtcclxufVxyXG5cclxuZnVuY3Rpb24gY2FuTW92ZShkYXRhLCBvcmlnLCBkZXN0KSB7XHJcbiAgcmV0dXJuIG9yaWcgIT09IGRlc3QgJiYgaXNNb3ZhYmxlKGRhdGEsIG9yaWcpICYmIChcclxuICAgIGRhdGEubW92YWJsZS5mcmVlIHx8IHV0aWwuY29udGFpbnNYKGRhdGEubW92YWJsZS5kZXN0c1tvcmlnXSwgZGVzdClcclxuICApO1xyXG59XHJcblxyXG5mdW5jdGlvbiBjYW5Ecm9wKGRhdGEsIG9yaWcsIGRlc3QpIHtcclxuICB2YXIgcGllY2UgPSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICByZXR1cm4gcGllY2UgJiYgZGVzdCAmJiAob3JpZyA9PT0gZGVzdCB8fCAhZGF0YS5waWVjZXNbZGVzdF0pICYmIChcclxuICAgIGRhdGEubW92YWJsZS5jb2xvciA9PT0gJ2JvdGgnIHx8IChcclxuICAgICAgZGF0YS5tb3ZhYmxlLmNvbG9yID09PSBwaWVjZS5jb2xvciAmJlxyXG4gICAgICBkYXRhLnR1cm5Db2xvciA9PT0gcGllY2UuY29sb3JcclxuICAgICkpO1xyXG59XHJcblxyXG5cclxuZnVuY3Rpb24gaXNQcmVtb3ZhYmxlKGRhdGEsIG9yaWcpIHtcclxuICB2YXIgcGllY2UgPSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICByZXR1cm4gcGllY2UgJiYgZGF0YS5wcmVtb3ZhYmxlLmVuYWJsZWQgJiZcclxuICAgIGRhdGEubW92YWJsZS5jb2xvciA9PT0gcGllY2UuY29sb3IgJiZcclxuICAgIGRhdGEudHVybkNvbG9yICE9PSBwaWVjZS5jb2xvcjtcclxufVxyXG5cclxuZnVuY3Rpb24gY2FuUHJlbW92ZShkYXRhLCBvcmlnLCBkZXN0KSB7XHJcbiAgcmV0dXJuIG9yaWcgIT09IGRlc3QgJiZcclxuICAgIGlzUHJlbW92YWJsZShkYXRhLCBvcmlnKSAmJlxyXG4gICAgdXRpbC5jb250YWluc1gocHJlbW92ZShkYXRhLnBpZWNlcywgb3JpZywgZGF0YS5wcmVtb3ZhYmxlLmNhc3RsZSksIGRlc3QpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBjYW5QcmVkcm9wKGRhdGEsIG9yaWcsIGRlc3QpIHtcclxuICB2YXIgcGllY2UgPSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICByZXR1cm4gcGllY2UgJiYgZGVzdCAmJlxyXG4gICAgKCFkYXRhLnBpZWNlc1tkZXN0XSB8fCBkYXRhLnBpZWNlc1tkZXN0XS5jb2xvciAhPT0gZGF0YS5tb3ZhYmxlLmNvbG9yKSAmJlxyXG4gICAgZGF0YS5wcmVkcm9wcGFibGUuZW5hYmxlZCAmJlxyXG4gICAgKHBpZWNlLnJvbGUgIT09ICdwYXduJyB8fCAoZGVzdFsxXSAhPT0gJzEnICYmIGRlc3RbMV0gIT09ICc4JykpICYmXHJcbiAgICBkYXRhLm1vdmFibGUuY29sb3IgPT09IHBpZWNlLmNvbG9yICYmXHJcbiAgICBkYXRhLnR1cm5Db2xvciAhPT0gcGllY2UuY29sb3I7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGlzRHJhZ2dhYmxlKGRhdGEsIG9yaWcpIHtcclxuICB2YXIgcGllY2UgPSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICByZXR1cm4gcGllY2UgJiYgZGF0YS5kcmFnZ2FibGUuZW5hYmxlZCAmJiAoXHJcbiAgICBkYXRhLm1vdmFibGUuY29sb3IgPT09ICdib3RoJyB8fCAoXHJcbiAgICAgIGRhdGEubW92YWJsZS5jb2xvciA9PT0gcGllY2UuY29sb3IgJiYgKFxyXG4gICAgICAgIGRhdGEudHVybkNvbG9yID09PSBwaWVjZS5jb2xvciB8fCBkYXRhLnByZW1vdmFibGUuZW5hYmxlZFxyXG4gICAgICApXHJcbiAgICApXHJcbiAgKTtcclxufVxyXG5cclxuZnVuY3Rpb24gcGxheVByZW1vdmUoZGF0YSkge1xyXG4gIHZhciBtb3ZlID0gZGF0YS5wcmVtb3ZhYmxlLmN1cnJlbnQ7XHJcbiAgaWYgKCFtb3ZlKSByZXR1cm47XHJcbiAgdmFyIG9yaWcgPSBtb3ZlWzBdLFxyXG4gICAgZGVzdCA9IG1vdmVbMV0sXHJcbiAgICBzdWNjZXNzID0gZmFsc2U7XHJcbiAgaWYgKGNhbk1vdmUoZGF0YSwgb3JpZywgZGVzdCkpIHtcclxuICAgIGlmIChiYXNlVXNlck1vdmUoZGF0YSwgb3JpZywgZGVzdCkpIHtcclxuICAgICAgY2FsbFVzZXJGdW5jdGlvbih1dGlsLnBhcnRpYWwoZGF0YS5tb3ZhYmxlLmV2ZW50cy5hZnRlciwgb3JpZywgZGVzdCwge1xyXG4gICAgICAgIHByZW1vdmU6IHRydWVcclxuICAgICAgfSkpO1xyXG4gICAgICBzdWNjZXNzID0gdHJ1ZTtcclxuICAgIH1cclxuICB9XHJcbiAgdW5zZXRQcmVtb3ZlKGRhdGEpO1xyXG4gIHJldHVybiBzdWNjZXNzO1xyXG59XHJcblxyXG5mdW5jdGlvbiBwbGF5UHJlZHJvcChkYXRhLCB2YWxpZGF0ZSkge1xyXG4gIHZhciBkcm9wID0gZGF0YS5wcmVkcm9wcGFibGUuY3VycmVudCxcclxuICAgIHN1Y2Nlc3MgPSBmYWxzZTtcclxuICBpZiAoIWRyb3Aua2V5KSByZXR1cm47XHJcbiAgaWYgKHZhbGlkYXRlKGRyb3ApKSB7XHJcbiAgICB2YXIgcGllY2UgPSB7XHJcbiAgICAgIHJvbGU6IGRyb3Aucm9sZSxcclxuICAgICAgY29sb3I6IGRhdGEubW92YWJsZS5jb2xvclxyXG4gICAgfTtcclxuICAgIGlmIChiYXNlTmV3UGllY2UoZGF0YSwgcGllY2UsIGRyb3Aua2V5KSkge1xyXG4gICAgICBjYWxsVXNlckZ1bmN0aW9uKHV0aWwucGFydGlhbChkYXRhLm1vdmFibGUuZXZlbnRzLmFmdGVyTmV3UGllY2UsIGRyb3Aucm9sZSwgZHJvcC5rZXksIHtcclxuICAgICAgICBwcmVkcm9wOiB0cnVlXHJcbiAgICAgIH0pKTtcclxuICAgICAgc3VjY2VzcyA9IHRydWU7XHJcbiAgICB9XHJcbiAgfVxyXG4gIHVuc2V0UHJlZHJvcChkYXRhKTtcclxuICByZXR1cm4gc3VjY2VzcztcclxufVxyXG5cclxuZnVuY3Rpb24gY2FuY2VsTW92ZShkYXRhKSB7XHJcbiAgdW5zZXRQcmVtb3ZlKGRhdGEpO1xyXG4gIHVuc2V0UHJlZHJvcChkYXRhKTtcclxuICBzZWxlY3RTcXVhcmUoZGF0YSwgbnVsbCk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHN0b3AoZGF0YSkge1xyXG4gIGRhdGEubW92YWJsZS5jb2xvciA9IG51bGw7XHJcbiAgZGF0YS5tb3ZhYmxlLmRlc3RzID0ge307XHJcbiAgY2FuY2VsTW92ZShkYXRhKTtcclxufVxyXG5cclxuZnVuY3Rpb24gZ2V0S2V5QXREb21Qb3MoZGF0YSwgcG9zLCBib3VuZHMpIHtcclxuICBpZiAoIWJvdW5kcyAmJiAhZGF0YS5ib3VuZHMpIHJldHVybjtcclxuICBib3VuZHMgPSBib3VuZHMgfHwgZGF0YS5ib3VuZHMoKTsgLy8gdXNlIHByb3ZpZGVkIHZhbHVlLCBvciBjb21wdXRlIGl0XHJcbiAgdmFyIGZpbGUgPSBNYXRoLmNlaWwoOCAqICgocG9zWzBdIC0gYm91bmRzLmxlZnQpIC8gYm91bmRzLndpZHRoKSk7XHJcbiAgZmlsZSA9IGRhdGEub3JpZW50YXRpb24gPT09ICd3aGl0ZScgPyBmaWxlIDogOSAtIGZpbGU7XHJcbiAgdmFyIHJhbmsgPSBNYXRoLmNlaWwoOCAtICg4ICogKChwb3NbMV0gLSBib3VuZHMudG9wKSAvIGJvdW5kcy5oZWlnaHQpKSk7XHJcbiAgcmFuayA9IGRhdGEub3JpZW50YXRpb24gPT09ICd3aGl0ZScgPyByYW5rIDogOSAtIHJhbms7XHJcbiAgaWYgKGZpbGUgPiAwICYmIGZpbGUgPCA5ICYmIHJhbmsgPiAwICYmIHJhbmsgPCA5KSByZXR1cm4gdXRpbC5wb3Mya2V5KFtmaWxlLCByYW5rXSk7XHJcbn1cclxuXHJcbi8vIHt3aGl0ZToge3Bhd246IDMgcXVlZW46IDF9LCBibGFjazoge2Jpc2hvcDogMn19XHJcbmZ1bmN0aW9uIGdldE1hdGVyaWFsRGlmZihkYXRhKSB7XHJcbiAgdmFyIGNvdW50cyA9IHtcclxuICAgIGtpbmc6IDAsXHJcbiAgICBxdWVlbjogMCxcclxuICAgIHJvb2s6IDAsXHJcbiAgICBiaXNob3A6IDAsXHJcbiAgICBrbmlnaHQ6IDAsXHJcbiAgICBwYXduOiAwXHJcbiAgfTtcclxuICBmb3IgKHZhciBrIGluIGRhdGEucGllY2VzKSB7XHJcbiAgICB2YXIgcCA9IGRhdGEucGllY2VzW2tdO1xyXG4gICAgY291bnRzW3Aucm9sZV0gKz0gKChwLmNvbG9yID09PSAnd2hpdGUnKSA/IDEgOiAtMSk7XHJcbiAgfVxyXG4gIHZhciBkaWZmID0ge1xyXG4gICAgd2hpdGU6IHt9LFxyXG4gICAgYmxhY2s6IHt9XHJcbiAgfTtcclxuICBmb3IgKHZhciByb2xlIGluIGNvdW50cykge1xyXG4gICAgdmFyIGMgPSBjb3VudHNbcm9sZV07XHJcbiAgICBpZiAoYyA+IDApIGRpZmYud2hpdGVbcm9sZV0gPSBjO1xyXG4gICAgZWxzZSBpZiAoYyA8IDApIGRpZmYuYmxhY2tbcm9sZV0gPSAtYztcclxuICB9XHJcbiAgcmV0dXJuIGRpZmY7XHJcbn1cclxuXHJcbnZhciBwaWVjZVNjb3JlcyA9IHtcclxuICBwYXduOiAxLFxyXG4gIGtuaWdodDogMyxcclxuICBiaXNob3A6IDMsXHJcbiAgcm9vazogNSxcclxuICBxdWVlbjogOSxcclxuICBraW5nOiAwXHJcbn07XHJcblxyXG5mdW5jdGlvbiBnZXRTY29yZShkYXRhKSB7XHJcbiAgdmFyIHNjb3JlID0gMDtcclxuICBmb3IgKHZhciBrIGluIGRhdGEucGllY2VzKSB7XHJcbiAgICBzY29yZSArPSBwaWVjZVNjb3Jlc1tkYXRhLnBpZWNlc1trXS5yb2xlXSAqIChkYXRhLnBpZWNlc1trXS5jb2xvciA9PT0gJ3doaXRlJyA/IDEgOiAtMSk7XHJcbiAgfVxyXG4gIHJldHVybiBzY29yZTtcclxufVxyXG5cclxubW9kdWxlLmV4cG9ydHMgPSB7XHJcbiAgcmVzZXQ6IHJlc2V0LFxyXG4gIHRvZ2dsZU9yaWVudGF0aW9uOiB0b2dnbGVPcmllbnRhdGlvbixcclxuICBzZXRQaWVjZXM6IHNldFBpZWNlcyxcclxuICBzZXRDaGVjazogc2V0Q2hlY2ssXHJcbiAgc2VsZWN0U3F1YXJlOiBzZWxlY3RTcXVhcmUsXHJcbiAgc2V0U2VsZWN0ZWQ6IHNldFNlbGVjdGVkLFxyXG4gIGlzRHJhZ2dhYmxlOiBpc0RyYWdnYWJsZSxcclxuICBjYW5Nb3ZlOiBjYW5Nb3ZlLFxyXG4gIHVzZXJNb3ZlOiB1c2VyTW92ZSxcclxuICBkcm9wTmV3UGllY2U6IGRyb3BOZXdQaWVjZSxcclxuICBhcGlNb3ZlOiBhcGlNb3ZlLFxyXG4gIGFwaU5ld1BpZWNlOiBhcGlOZXdQaWVjZSxcclxuICBwbGF5UHJlbW92ZTogcGxheVByZW1vdmUsXHJcbiAgcGxheVByZWRyb3A6IHBsYXlQcmVkcm9wLFxyXG4gIHVuc2V0UHJlbW92ZTogdW5zZXRQcmVtb3ZlLFxyXG4gIHVuc2V0UHJlZHJvcDogdW5zZXRQcmVkcm9wLFxyXG4gIGNhbmNlbE1vdmU6IGNhbmNlbE1vdmUsXHJcbiAgc3RvcDogc3RvcCxcclxuICBnZXRLZXlBdERvbVBvczogZ2V0S2V5QXREb21Qb3MsXHJcbiAgZ2V0TWF0ZXJpYWxEaWZmOiBnZXRNYXRlcmlhbERpZmYsXHJcbiAgZ2V0U2NvcmU6IGdldFNjb3JlXHJcbn07XHJcbiIsInZhciBtZXJnZSA9IHJlcXVpcmUoJ21lcmdlJyk7XHJcbnZhciBib2FyZCA9IHJlcXVpcmUoJy4vYm9hcmQnKTtcclxudmFyIGZlbiA9IHJlcXVpcmUoJy4vZmVuJyk7XHJcblxyXG5tb2R1bGUuZXhwb3J0cyA9IGZ1bmN0aW9uKGRhdGEsIGNvbmZpZykge1xyXG5cclxuICBpZiAoIWNvbmZpZykgcmV0dXJuO1xyXG5cclxuICAvLyBkb24ndCBtZXJnZSBkZXN0aW5hdGlvbnMuIEp1c3Qgb3ZlcnJpZGUuXHJcbiAgaWYgKGNvbmZpZy5tb3ZhYmxlICYmIGNvbmZpZy5tb3ZhYmxlLmRlc3RzKSBkZWxldGUgZGF0YS5tb3ZhYmxlLmRlc3RzO1xyXG5cclxuICBtZXJnZS5yZWN1cnNpdmUoZGF0YSwgY29uZmlnKTtcclxuXHJcbiAgLy8gaWYgYSBmZW4gd2FzIHByb3ZpZGVkLCByZXBsYWNlIHRoZSBwaWVjZXNcclxuICBpZiAoZGF0YS5mZW4pIHtcclxuICAgIGRhdGEucGllY2VzID0gZmVuLnJlYWQoZGF0YS5mZW4pO1xyXG4gICAgZGF0YS5jaGVjayA9IGNvbmZpZy5jaGVjaztcclxuICAgIGRhdGEuZHJhd2FibGUuc2hhcGVzID0gW107XHJcbiAgICBkZWxldGUgZGF0YS5mZW47XHJcbiAgfVxyXG5cclxuICBpZiAoZGF0YS5jaGVjayA9PT0gdHJ1ZSkgYm9hcmQuc2V0Q2hlY2soZGF0YSk7XHJcblxyXG4gIC8vIGZvcmdldCBhYm91dCB0aGUgbGFzdCBkcm9wcGVkIHBpZWNlXHJcbiAgZGF0YS5tb3ZhYmxlLmRyb3BwZWQgPSBbXTtcclxuXHJcbiAgLy8gZml4IG1vdmUvcHJlbW92ZSBkZXN0c1xyXG4gIGlmIChkYXRhLnNlbGVjdGVkKSBib2FyZC5zZXRTZWxlY3RlZChkYXRhLCBkYXRhLnNlbGVjdGVkKTtcclxuXHJcbiAgLy8gbm8gbmVlZCBmb3Igc3VjaCBzaG9ydCBhbmltYXRpb25zXHJcbiAgaWYgKCFkYXRhLmFuaW1hdGlvbi5kdXJhdGlvbiB8fCBkYXRhLmFuaW1hdGlvbi5kdXJhdGlvbiA8IDQwKVxyXG4gICAgZGF0YS5hbmltYXRpb24uZW5hYmxlZCA9IGZhbHNlO1xyXG59O1xyXG4iLCJ2YXIgbSA9IHJlcXVpcmUoJ21pdGhyaWwnKTtcclxudmFyIHV0aWwgPSByZXF1aXJlKCcuL3V0aWwnKTtcclxuXHJcbmZ1bmN0aW9uIHJlbmRlckNvb3JkcyhlbGVtcywga2xhc3MsIG9yaWVudCkge1xyXG4gIHZhciBlbCA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2Nvb3JkcycpO1xyXG4gIGVsLmNsYXNzTmFtZSA9IGtsYXNzO1xyXG4gIGVsZW1zLmZvckVhY2goZnVuY3Rpb24oY29udGVudCkge1xyXG4gICAgdmFyIGYgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdjb29yZCcpO1xyXG4gICAgZi50ZXh0Q29udGVudCA9IGNvbnRlbnQ7XHJcbiAgICBlbC5hcHBlbmRDaGlsZChmKTtcclxuICB9KTtcclxuICByZXR1cm4gZWw7XHJcbn1cclxuXHJcbm1vZHVsZS5leHBvcnRzID0gZnVuY3Rpb24ob3JpZW50YXRpb24sIGVsKSB7XHJcblxyXG4gIHV0aWwucmVxdWVzdEFuaW1hdGlvbkZyYW1lKGZ1bmN0aW9uKCkge1xyXG4gICAgdmFyIGNvb3JkcyA9IGRvY3VtZW50LmNyZWF0ZURvY3VtZW50RnJhZ21lbnQoKTtcclxuICAgIHZhciBvcmllbnRDbGFzcyA9IG9yaWVudGF0aW9uID09PSAnYmxhY2snID8gJyBibGFjaycgOiAnJztcclxuICAgIGNvb3Jkcy5hcHBlbmRDaGlsZChyZW5kZXJDb29yZHModXRpbC5yYW5rcywgJ3JhbmtzJyArIG9yaWVudENsYXNzKSk7XHJcbiAgICBjb29yZHMuYXBwZW5kQ2hpbGQocmVuZGVyQ29vcmRzKHV0aWwuZmlsZXMsICdmaWxlcycgKyBvcmllbnRDbGFzcykpO1xyXG4gICAgZWwuYXBwZW5kQ2hpbGQoY29vcmRzKTtcclxuICB9KTtcclxuXHJcbiAgdmFyIG9yaWVudGF0aW9uO1xyXG5cclxuICByZXR1cm4gZnVuY3Rpb24obykge1xyXG4gICAgaWYgKG8gPT09IG9yaWVudGF0aW9uKSByZXR1cm47XHJcbiAgICBvcmllbnRhdGlvbiA9IG87XHJcbiAgICAkKGVsKS5maW5kKCdjb29yZHMnKS50b2dnbGVDbGFzcygnYmxhY2snLCBvcmllbnRhdGlvbiA9PT0gJ2JsYWNrJyk7XHJcbiAgfTtcclxufVxyXG4iLCJ2YXIgYm9hcmQgPSByZXF1aXJlKCcuL2JvYXJkJyk7XHJcbnZhciBkYXRhID0gcmVxdWlyZSgnLi9kYXRhJyk7XHJcbnZhciBmZW4gPSByZXF1aXJlKCcuL2ZlbicpO1xyXG52YXIgY29uZmlndXJlID0gcmVxdWlyZSgnLi9jb25maWd1cmUnKTtcclxudmFyIGFuaW0gPSByZXF1aXJlKCcuL2FuaW0nKTtcclxudmFyIGRyYWcgPSByZXF1aXJlKCcuL2RyYWcnKTtcclxuXHJcbm1vZHVsZS5leHBvcnRzID0gZnVuY3Rpb24oY2ZnKSB7XHJcblxyXG4gIHRoaXMuZGF0YSA9IGRhdGEoY2ZnKTtcclxuXHJcbiAgdGhpcy52bSA9IHtcclxuICAgIGV4cGxvZGluZzogZmFsc2VcclxuICB9O1xyXG5cclxuICB0aGlzLmdldEZlbiA9IGZ1bmN0aW9uKCkge1xyXG4gICAgcmV0dXJuIGZlbi53cml0ZSh0aGlzLmRhdGEucGllY2VzKTtcclxuICB9LmJpbmQodGhpcyk7XHJcblxyXG4gIHRoaXMuZ2V0T3JpZW50YXRpb24gPSBmdW5jdGlvbigpIHtcclxuICAgIHJldHVybiB0aGlzLmRhdGEub3JpZW50YXRpb247XHJcbiAgfS5iaW5kKHRoaXMpO1xyXG5cclxuICB0aGlzLnNldCA9IGFuaW0oY29uZmlndXJlLCB0aGlzLmRhdGEpO1xyXG5cclxuICB0aGlzLnRvZ2dsZU9yaWVudGF0aW9uID0gYW5pbShib2FyZC50b2dnbGVPcmllbnRhdGlvbiwgdGhpcy5kYXRhKTtcclxuXHJcbiAgdGhpcy5zZXRQaWVjZXMgPSBhbmltKGJvYXJkLnNldFBpZWNlcywgdGhpcy5kYXRhKTtcclxuXHJcbiAgdGhpcy5zZWxlY3RTcXVhcmUgPSBhbmltKGJvYXJkLnNlbGVjdFNxdWFyZSwgdGhpcy5kYXRhLCB0cnVlKTtcclxuXHJcbiAgdGhpcy5hcGlNb3ZlID0gYW5pbShib2FyZC5hcGlNb3ZlLCB0aGlzLmRhdGEpO1xyXG5cclxuICB0aGlzLmFwaU5ld1BpZWNlID0gYW5pbShib2FyZC5hcGlOZXdQaWVjZSwgdGhpcy5kYXRhKTtcclxuXHJcbiAgdGhpcy5wbGF5UHJlbW92ZSA9IGFuaW0oYm9hcmQucGxheVByZW1vdmUsIHRoaXMuZGF0YSk7XHJcblxyXG4gIHRoaXMucGxheVByZWRyb3AgPSBhbmltKGJvYXJkLnBsYXlQcmVkcm9wLCB0aGlzLmRhdGEpO1xyXG5cclxuICB0aGlzLmNhbmNlbFByZW1vdmUgPSBhbmltKGJvYXJkLnVuc2V0UHJlbW92ZSwgdGhpcy5kYXRhLCB0cnVlKTtcclxuXHJcbiAgdGhpcy5jYW5jZWxQcmVkcm9wID0gYW5pbShib2FyZC51bnNldFByZWRyb3AsIHRoaXMuZGF0YSwgdHJ1ZSk7XHJcblxyXG4gIHRoaXMuc2V0Q2hlY2sgPSBhbmltKGJvYXJkLnNldENoZWNrLCB0aGlzLmRhdGEsIHRydWUpO1xyXG5cclxuICB0aGlzLmNhbmNlbE1vdmUgPSBhbmltKGZ1bmN0aW9uKGRhdGEpIHtcclxuICAgIGJvYXJkLmNhbmNlbE1vdmUoZGF0YSk7XHJcbiAgICBkcmFnLmNhbmNlbChkYXRhKTtcclxuICB9LmJpbmQodGhpcyksIHRoaXMuZGF0YSwgdHJ1ZSk7XHJcblxyXG4gIHRoaXMuc3RvcCA9IGFuaW0oZnVuY3Rpb24oZGF0YSkge1xyXG4gICAgYm9hcmQuc3RvcChkYXRhKTtcclxuICAgIGRyYWcuY2FuY2VsKGRhdGEpO1xyXG4gIH0uYmluZCh0aGlzKSwgdGhpcy5kYXRhLCB0cnVlKTtcclxuXHJcbiAgdGhpcy5leHBsb2RlID0gZnVuY3Rpb24oa2V5cykge1xyXG4gICAgaWYgKCF0aGlzLmRhdGEucmVuZGVyKSByZXR1cm47XHJcbiAgICB0aGlzLnZtLmV4cGxvZGluZyA9IHtcclxuICAgICAgc3RhZ2U6IDEsXHJcbiAgICAgIGtleXM6IGtleXNcclxuICAgIH07XHJcbiAgICB0aGlzLmRhdGEucmVuZGVyUkFGKCk7XHJcbiAgICBzZXRUaW1lb3V0KGZ1bmN0aW9uKCkge1xyXG4gICAgICB0aGlzLnZtLmV4cGxvZGluZy5zdGFnZSA9IDI7XHJcbiAgICAgIHRoaXMuZGF0YS5yZW5kZXJSQUYoKTtcclxuICAgICAgc2V0VGltZW91dChmdW5jdGlvbigpIHtcclxuICAgICAgICB0aGlzLnZtLmV4cGxvZGluZyA9IGZhbHNlO1xyXG4gICAgICAgIHRoaXMuZGF0YS5yZW5kZXJSQUYoKTtcclxuICAgICAgfS5iaW5kKHRoaXMpLCAxMjApO1xyXG4gICAgfS5iaW5kKHRoaXMpLCAxMjApO1xyXG4gIH0uYmluZCh0aGlzKTtcclxuXHJcbiAgdGhpcy5zZXRBdXRvU2hhcGVzID0gZnVuY3Rpb24oc2hhcGVzKSB7XHJcbiAgICBhbmltKGZ1bmN0aW9uKGRhdGEpIHtcclxuICAgICAgZGF0YS5kcmF3YWJsZS5hdXRvU2hhcGVzID0gc2hhcGVzO1xyXG4gICAgfSwgdGhpcy5kYXRhLCBmYWxzZSkoKTtcclxuICB9LmJpbmQodGhpcyk7XHJcblxyXG4gIHRoaXMuc2V0U2hhcGVzID0gZnVuY3Rpb24oc2hhcGVzKSB7XHJcbiAgICBhbmltKGZ1bmN0aW9uKGRhdGEpIHtcclxuICAgICAgZGF0YS5kcmF3YWJsZS5zaGFwZXMgPSBzaGFwZXM7XHJcbiAgICB9LCB0aGlzLmRhdGEsIGZhbHNlKSgpO1xyXG4gIH0uYmluZCh0aGlzKTtcclxufTtcclxuIiwidmFyIGZlbiA9IHJlcXVpcmUoJy4vZmVuJyk7XHJcbnZhciBjb25maWd1cmUgPSByZXF1aXJlKCcuL2NvbmZpZ3VyZScpO1xyXG5cclxubW9kdWxlLmV4cG9ydHMgPSBmdW5jdGlvbihjZmcpIHtcclxuICB2YXIgZGVmYXVsdHMgPSB7XHJcbiAgICBwaWVjZXM6IGZlbi5yZWFkKGZlbi5pbml0aWFsKSxcclxuICAgIG9yaWVudGF0aW9uOiAnd2hpdGUnLCAvLyBib2FyZCBvcmllbnRhdGlvbi4gd2hpdGUgfCBibGFja1xyXG4gICAgdHVybkNvbG9yOiAnd2hpdGUnLCAvLyB0dXJuIHRvIHBsYXkuIHdoaXRlIHwgYmxhY2tcclxuICAgIGNoZWNrOiBudWxsLCAvLyBzcXVhcmUgY3VycmVudGx5IGluIGNoZWNrIFwiYTJcIiB8IG51bGxcclxuICAgIGxhc3RNb3ZlOiBudWxsLCAvLyBzcXVhcmVzIHBhcnQgb2YgdGhlIGxhc3QgbW92ZSBbXCJjM1wiLCBcImM0XCJdIHwgbnVsbFxyXG4gICAgc2VsZWN0ZWQ6IG51bGwsIC8vIHNxdWFyZSBjdXJyZW50bHkgc2VsZWN0ZWQgXCJhMVwiIHwgbnVsbFxyXG4gICAgY29vcmRpbmF0ZXM6IHRydWUsIC8vIGluY2x1ZGUgY29vcmRzIGF0dHJpYnV0ZXNcclxuICAgIHJlbmRlcjogbnVsbCwgLy8gZnVuY3Rpb24gdGhhdCByZXJlbmRlcnMgdGhlIGJvYXJkXHJcbiAgICByZW5kZXJSQUY6IG51bGwsIC8vIGZ1bmN0aW9uIHRoYXQgcmVyZW5kZXJzIHRoZSBib2FyZCB1c2luZyByZXF1ZXN0QW5pbWF0aW9uRnJhbWVcclxuICAgIGVsZW1lbnQ6IG51bGwsIC8vIERPTSBlbGVtZW50IG9mIHRoZSBib2FyZCwgcmVxdWlyZWQgZm9yIGRyYWcgcGllY2UgY2VudGVyaW5nXHJcbiAgICBib3VuZHM6IG51bGwsIC8vIGZ1bmN0aW9uIHRoYXQgY2FsY3VsYXRlcyB0aGUgYm9hcmQgYm91bmRzXHJcbiAgICBhdXRvQ2FzdGxlOiBmYWxzZSwgLy8gaW1tZWRpYXRlbHkgY29tcGxldGUgdGhlIGNhc3RsZSBieSBtb3ZpbmcgdGhlIHJvb2sgYWZ0ZXIga2luZyBtb3ZlXHJcbiAgICB2aWV3T25seTogZmFsc2UsIC8vIGRvbid0IGJpbmQgZXZlbnRzOiB0aGUgdXNlciB3aWxsIG5ldmVyIGJlIGFibGUgdG8gbW92ZSBwaWVjZXMgYXJvdW5kXHJcbiAgICBkaXNhYmxlQ29udGV4dE1lbnU6IGZhbHNlLCAvLyBiZWNhdXNlIHdobyBuZWVkcyBhIGNvbnRleHQgbWVudSBvbiBhIGNoZXNzYm9hcmRcclxuICAgIHJlc2l6YWJsZTogdHJ1ZSwgLy8gbGlzdGVucyB0byBjaGVzc2dyb3VuZC5yZXNpemUgb24gZG9jdW1lbnQuYm9keSB0byBjbGVhciBib3VuZHMgY2FjaGVcclxuICAgIHBpZWNlS2V5OiBmYWxzZSwgLy8gYWRkIGEgZGF0YS1rZXkgYXR0cmlidXRlIHRvIHBpZWNlIGVsZW1lbnRzXHJcbiAgICBoaWdobGlnaHQ6IHtcclxuICAgICAgbGFzdE1vdmU6IHRydWUsIC8vIGFkZCBsYXN0LW1vdmUgY2xhc3MgdG8gc3F1YXJlc1xyXG4gICAgICBjaGVjazogdHJ1ZSwgLy8gYWRkIGNoZWNrIGNsYXNzIHRvIHNxdWFyZXNcclxuICAgICAgZHJhZ092ZXI6IHRydWUgLy8gYWRkIGRyYWctb3ZlciBjbGFzcyB0byBzcXVhcmUgd2hlbiBkcmFnZ2luZyBvdmVyIGl0XHJcbiAgICB9LFxyXG4gICAgYW5pbWF0aW9uOiB7XHJcbiAgICAgIGVuYWJsZWQ6IHRydWUsXHJcbiAgICAgIGR1cmF0aW9uOiAyMDAsXHJcbiAgICAgIC8qeyAvLyBjdXJyZW50XHJcbiAgICAgICAqICBzdGFydDogdGltZXN0YW1wLFxyXG4gICAgICAgKiAgZHVyYXRpb246IG1zLFxyXG4gICAgICAgKiAgYW5pbXM6IHtcclxuICAgICAgICogICAgYTI6IFtcclxuICAgICAgICogICAgICBbLTMwLCA1MF0sIC8vIGFuaW1hdGlvbiBnb2FsXHJcbiAgICAgICAqICAgICAgWy0yMCwgMzddICAvLyBhbmltYXRpb24gY3VycmVudCBzdGF0dXNcclxuICAgICAgICogICAgXSwgLi4uXHJcbiAgICAgICAqICB9LFxyXG4gICAgICAgKiAgZmFkaW5nOiBbXHJcbiAgICAgICAqICAgIHtcclxuICAgICAgICogICAgICBwb3M6IFs4MCwgMTIwXSwgLy8gcG9zaXRpb24gcmVsYXRpdmUgdG8gdGhlIGJvYXJkXHJcbiAgICAgICAqICAgICAgb3BhY2l0eTogMC4zNCxcclxuICAgICAgICogICAgICByb2xlOiAncm9vaycsXHJcbiAgICAgICAqICAgICAgY29sb3I6ICdibGFjaydcclxuICAgICAgICogICAgfVxyXG4gICAgICAgKiAgfVxyXG4gICAgICAgKn0qL1xyXG4gICAgICBjdXJyZW50OiB7fVxyXG4gICAgfSxcclxuICAgIG1vdmFibGU6IHtcclxuICAgICAgZnJlZTogdHJ1ZSwgLy8gYWxsIG1vdmVzIGFyZSB2YWxpZCAtIGJvYXJkIGVkaXRvclxyXG4gICAgICBjb2xvcjogJ2JvdGgnLCAvLyBjb2xvciB0aGF0IGNhbiBtb3ZlLiB3aGl0ZSB8IGJsYWNrIHwgYm90aCB8IG51bGxcclxuICAgICAgZGVzdHM6IHt9LCAvLyB2YWxpZCBtb3Zlcy4ge1wiYTJcIiBbXCJhM1wiIFwiYTRcIl0gXCJiMVwiIFtcImEzXCIgXCJjM1wiXX0gfCBudWxsXHJcbiAgICAgIGRyb3BPZmY6ICdyZXZlcnQnLCAvLyB3aGVuIGEgcGllY2UgaXMgZHJvcHBlZCBvdXRzaWRlIHRoZSBib2FyZC4gXCJyZXZlcnRcIiB8IFwidHJhc2hcIlxyXG4gICAgICBkcm9wcGVkOiBbXSwgLy8gbGFzdCBkcm9wcGVkIFtvcmlnLCBkZXN0XSwgbm90IHRvIGJlIGFuaW1hdGVkXHJcbiAgICAgIHNob3dEZXN0czogdHJ1ZSwgLy8gd2hldGhlciB0byBhZGQgdGhlIG1vdmUtZGVzdCBjbGFzcyBvbiBzcXVhcmVzXHJcbiAgICAgIGV2ZW50czoge1xyXG4gICAgICAgIGFmdGVyOiBmdW5jdGlvbihvcmlnLCBkZXN0LCBtZXRhZGF0YSkge30sIC8vIGNhbGxlZCBhZnRlciB0aGUgbW92ZSBoYXMgYmVlbiBwbGF5ZWRcclxuICAgICAgICBhZnRlck5ld1BpZWNlOiBmdW5jdGlvbihyb2xlLCBwb3MpIHt9IC8vIGNhbGxlZCBhZnRlciBhIG5ldyBwaWVjZSBpcyBkcm9wcGVkIG9uIHRoZSBib2FyZFxyXG4gICAgICB9XHJcbiAgICB9LFxyXG4gICAgcHJlbW92YWJsZToge1xyXG4gICAgICBlbmFibGVkOiB0cnVlLCAvLyBhbGxvdyBwcmVtb3ZlcyBmb3IgY29sb3IgdGhhdCBjYW4gbm90IG1vdmVcclxuICAgICAgc2hvd0Rlc3RzOiB0cnVlLCAvLyB3aGV0aGVyIHRvIGFkZCB0aGUgcHJlbW92ZS1kZXN0IGNsYXNzIG9uIHNxdWFyZXNcclxuICAgICAgY2FzdGxlOiB0cnVlLCAvLyB3aGV0aGVyIHRvIGFsbG93IGtpbmcgY2FzdGxlIHByZW1vdmVzXHJcbiAgICAgIGRlc3RzOiBbXSwgLy8gcHJlbW92ZSBkZXN0aW5hdGlvbnMgZm9yIHRoZSBjdXJyZW50IHNlbGVjdGlvblxyXG4gICAgICBjdXJyZW50OiBudWxsLCAvLyBrZXlzIG9mIHRoZSBjdXJyZW50IHNhdmVkIHByZW1vdmUgW1wiZTJcIiBcImU0XCJdIHwgbnVsbFxyXG4gICAgICBldmVudHM6IHtcclxuICAgICAgICBzZXQ6IGZ1bmN0aW9uKG9yaWcsIGRlc3QpIHt9LCAvLyBjYWxsZWQgYWZ0ZXIgdGhlIHByZW1vdmUgaGFzIGJlZW4gc2V0XHJcbiAgICAgICAgdW5zZXQ6IGZ1bmN0aW9uKCkge30gLy8gY2FsbGVkIGFmdGVyIHRoZSBwcmVtb3ZlIGhhcyBiZWVuIHVuc2V0XHJcbiAgICAgIH1cclxuICAgIH0sXHJcbiAgICBwcmVkcm9wcGFibGU6IHtcclxuICAgICAgZW5hYmxlZDogZmFsc2UsIC8vIGFsbG93IHByZWRyb3BzIGZvciBjb2xvciB0aGF0IGNhbiBub3QgbW92ZVxyXG4gICAgICBjdXJyZW50OiB7fSwgLy8gY3VycmVudCBzYXZlZCBwcmVkcm9wIHtyb2xlOiAna25pZ2h0Jywga2V5OiAnZTQnfSB8IHt9XHJcbiAgICAgIGV2ZW50czoge1xyXG4gICAgICAgIHNldDogZnVuY3Rpb24ocm9sZSwga2V5KSB7fSwgLy8gY2FsbGVkIGFmdGVyIHRoZSBwcmVkcm9wIGhhcyBiZWVuIHNldFxyXG4gICAgICAgIHVuc2V0OiBmdW5jdGlvbigpIHt9IC8vIGNhbGxlZCBhZnRlciB0aGUgcHJlZHJvcCBoYXMgYmVlbiB1bnNldFxyXG4gICAgICB9XHJcbiAgICB9LFxyXG4gICAgZHJhZ2dhYmxlOiB7XHJcbiAgICAgIGVuYWJsZWQ6IHRydWUsIC8vIGFsbG93IG1vdmVzICYgcHJlbW92ZXMgdG8gdXNlIGRyYWcnbiBkcm9wXHJcbiAgICAgIGRpc3RhbmNlOiAzLCAvLyBtaW5pbXVtIGRpc3RhbmNlIHRvIGluaXRpYXRlIGEgZHJhZywgaW4gcGl4ZWxzXHJcbiAgICAgIGF1dG9EaXN0YW5jZTogdHJ1ZSwgLy8gbGV0cyBjaGVzc2dyb3VuZCBzZXQgZGlzdGFuY2UgdG8gemVybyB3aGVuIHVzZXIgZHJhZ3MgcGllY2VzXHJcbiAgICAgIGNlbnRlclBpZWNlOiB0cnVlLCAvLyBjZW50ZXIgdGhlIHBpZWNlIG9uIGN1cnNvciBhdCBkcmFnIHN0YXJ0XHJcbiAgICAgIHNob3dHaG9zdDogdHJ1ZSwgLy8gc2hvdyBnaG9zdCBvZiBwaWVjZSBiZWluZyBkcmFnZ2VkXHJcbiAgICAgIC8qeyAvLyBjdXJyZW50XHJcbiAgICAgICAqICBvcmlnOiBcImEyXCIsIC8vIG9yaWcga2V5IG9mIGRyYWdnaW5nIHBpZWNlXHJcbiAgICAgICAqICByZWw6IFsxMDAsIDE3MF0gLy8geCwgeSBvZiB0aGUgcGllY2UgYXQgb3JpZ2luYWwgcG9zaXRpb25cclxuICAgICAgICogIHBvczogWzIwLCAtMTJdIC8vIHJlbGF0aXZlIGN1cnJlbnQgcG9zaXRpb25cclxuICAgICAgICogIGRlYzogWzQsIC04XSAvLyBwaWVjZSBjZW50ZXIgZGVjYXlcclxuICAgICAgICogIG92ZXI6IFwiYjNcIiAvLyBzcXVhcmUgYmVpbmcgbW91c2VkIG92ZXJcclxuICAgICAgICogIGJvdW5kczogY3VycmVudCBjYWNoZWQgYm9hcmQgYm91bmRzXHJcbiAgICAgICAqICBzdGFydGVkOiB3aGV0aGVyIHRoZSBkcmFnIGhhcyBzdGFydGVkLCBhcyBwZXIgdGhlIGRpc3RhbmNlIHNldHRpbmdcclxuICAgICAgICp9Ki9cclxuICAgICAgY3VycmVudDoge31cclxuICAgIH0sXHJcbiAgICBzZWxlY3RhYmxlOiB7XHJcbiAgICAgIC8vIGRpc2FibGUgdG8gZW5mb3JjZSBkcmFnZ2luZyBvdmVyIGNsaWNrLWNsaWNrIG1vdmVcclxuICAgICAgZW5hYmxlZDogdHJ1ZVxyXG4gICAgfSxcclxuICAgIHN0YXRzOiB7XHJcbiAgICAgIC8vIHdhcyBsYXN0IHBpZWNlIGRyYWdnZWQgb3IgY2xpY2tlZD9cclxuICAgICAgLy8gbmVlZHMgZGVmYXVsdCB0byBmYWxzZSBmb3IgdG91Y2hcclxuICAgICAgZHJhZ2dlZDogISgnb250b3VjaHN0YXJ0JyBpbiB3aW5kb3cpXHJcbiAgICB9LFxyXG4gICAgZXZlbnRzOiB7XHJcbiAgICAgIGNoYW5nZTogZnVuY3Rpb24oKSB7fSwgLy8gY2FsbGVkIGFmdGVyIHRoZSBzaXR1YXRpb24gY2hhbmdlcyBvbiB0aGUgYm9hcmRcclxuICAgICAgLy8gY2FsbGVkIGFmdGVyIGEgcGllY2UgaGFzIGJlZW4gbW92ZWQuXHJcbiAgICAgIC8vIGNhcHR1cmVkUGllY2UgaXMgbnVsbCBvciBsaWtlIHtjb2xvcjogJ3doaXRlJywgJ3JvbGUnOiAncXVlZW4nfVxyXG4gICAgICBtb3ZlOiBmdW5jdGlvbihvcmlnLCBkZXN0LCBjYXB0dXJlZFBpZWNlKSB7fSxcclxuICAgICAgZHJvcE5ld1BpZWNlOiBmdW5jdGlvbihyb2xlLCBwb3MpIHt9LFxyXG4gICAgICBjYXB0dXJlOiBmdW5jdGlvbihrZXksIHBpZWNlKSB7fSwgLy8gREVQUkVDQVRFRCBjYWxsZWQgd2hlbiBhIHBpZWNlIGhhcyBiZWVuIGNhcHR1cmVkXHJcbiAgICAgIHNlbGVjdDogZnVuY3Rpb24oa2V5KSB7fSAvLyBjYWxsZWQgd2hlbiBhIHNxdWFyZSBpcyBzZWxlY3RlZFxyXG4gICAgfSxcclxuICAgIGl0ZW1zOiBudWxsLCAvLyBpdGVtcyBvbiB0aGUgYm9hcmQgeyByZW5kZXI6IGtleSAtPiB2ZG9tIH1cclxuICAgIGRyYXdhYmxlOiB7XHJcbiAgICAgIGVuYWJsZWQ6IGZhbHNlLCAvLyBhbGxvd3MgU1ZHIGRyYXdpbmdzXHJcbiAgICAgIGVyYXNlT25DbGljazogdHJ1ZSxcclxuICAgICAgb25DaGFuZ2U6IGZ1bmN0aW9uKHNoYXBlcykge30sXHJcbiAgICAgIC8vIHVzZXIgc2hhcGVzXHJcbiAgICAgIHNoYXBlczogW1xyXG4gICAgICAgIC8vIHticnVzaDogJ2dyZWVuJywgb3JpZzogJ2U4J30sXHJcbiAgICAgICAgLy8ge2JydXNoOiAneWVsbG93Jywgb3JpZzogJ2M0JywgZGVzdDogJ2Y3J31cclxuICAgICAgXSxcclxuICAgICAgLy8gY29tcHV0ZXIgc2hhcGVzXHJcbiAgICAgIGF1dG9TaGFwZXM6IFtcclxuICAgICAgICAvLyB7YnJ1c2g6ICdwYWxlQmx1ZScsIG9yaWc6ICdlOCd9LFxyXG4gICAgICAgIC8vIHticnVzaDogJ3BhbGVSZWQnLCBvcmlnOiAnYzQnLCBkZXN0OiAnZjcnfVxyXG4gICAgICBdLFxyXG4gICAgICAvKnsgLy8gY3VycmVudFxyXG4gICAgICAgKiAgb3JpZzogXCJhMlwiLCAvLyBvcmlnIGtleSBvZiBkcmF3aW5nXHJcbiAgICAgICAqICBwb3M6IFsyMCwgLTEyXSAvLyByZWxhdGl2ZSBjdXJyZW50IHBvc2l0aW9uXHJcbiAgICAgICAqICBkZXN0OiBcImIzXCIgLy8gc3F1YXJlIGJlaW5nIG1vdXNlZCBvdmVyXHJcbiAgICAgICAqICBib3VuZHM6IC8vIGN1cnJlbnQgY2FjaGVkIGJvYXJkIGJvdW5kc1xyXG4gICAgICAgKiAgYnJ1c2g6ICdncmVlbicgLy8gYnJ1c2ggbmFtZSBmb3Igc2hhcGVcclxuICAgICAgICp9Ki9cclxuICAgICAgY3VycmVudDoge30sXHJcbiAgICAgIGJydXNoZXM6IHtcclxuICAgICAgICBncmVlbjoge1xyXG4gICAgICAgICAga2V5OiAnZycsXHJcbiAgICAgICAgICBjb2xvcjogJyMxNTc4MUInLFxyXG4gICAgICAgICAgb3BhY2l0eTogMSxcclxuICAgICAgICAgIGxpbmVXaWR0aDogMTBcclxuICAgICAgICB9LFxyXG4gICAgICAgIHJlZDoge1xyXG4gICAgICAgICAga2V5OiAncicsXHJcbiAgICAgICAgICBjb2xvcjogJyM4ODIwMjAnLFxyXG4gICAgICAgICAgb3BhY2l0eTogMSxcclxuICAgICAgICAgIGxpbmVXaWR0aDogMTBcclxuICAgICAgICB9LFxyXG4gICAgICAgIGJsdWU6IHtcclxuICAgICAgICAgIGtleTogJ2InLFxyXG4gICAgICAgICAgY29sb3I6ICcjMDAzMDg4JyxcclxuICAgICAgICAgIG9wYWNpdHk6IDEsXHJcbiAgICAgICAgICBsaW5lV2lkdGg6IDEwXHJcbiAgICAgICAgfSxcclxuICAgICAgICB5ZWxsb3c6IHtcclxuICAgICAgICAgIGtleTogJ3knLFxyXG4gICAgICAgICAgY29sb3I6ICcjZTY4ZjAwJyxcclxuICAgICAgICAgIG9wYWNpdHk6IDEsXHJcbiAgICAgICAgICBsaW5lV2lkdGg6IDEwXHJcbiAgICAgICAgfSxcclxuICAgICAgICBwYWxlQmx1ZToge1xyXG4gICAgICAgICAga2V5OiAncGInLFxyXG4gICAgICAgICAgY29sb3I6ICcjMDAzMDg4JyxcclxuICAgICAgICAgIG9wYWNpdHk6IDAuMyxcclxuICAgICAgICAgIGxpbmVXaWR0aDogMTVcclxuICAgICAgICB9LFxyXG4gICAgICAgIHBhbGVHcmVlbjoge1xyXG4gICAgICAgICAga2V5OiAncGcnLFxyXG4gICAgICAgICAgY29sb3I6ICcjMTU3ODFCJyxcclxuICAgICAgICAgIG9wYWNpdHk6IDAuMzUsXHJcbiAgICAgICAgICBsaW5lV2lkdGg6IDE1XHJcbiAgICAgICAgfVxyXG4gICAgICB9LFxyXG4gICAgICAvLyBkcmF3YWJsZSBTVkcgcGllY2VzLCB1c2VkIGZvciBjcmF6eWhvdXNlIGRyb3BcclxuICAgICAgcGllY2VzOiB7XHJcbiAgICAgICAgYmFzZVVybDogJ2h0dHBzOi8vbGljaGVzczEub3JnL2Fzc2V0cy9waWVjZS9jYnVybmV0dC8nXHJcbiAgICAgIH1cclxuICAgIH1cclxuICB9O1xyXG5cclxuICBjb25maWd1cmUoZGVmYXVsdHMsIGNmZyB8fCB7fSk7XHJcblxyXG4gIHJldHVybiBkZWZhdWx0cztcclxufTtcclxuIiwidmFyIGJvYXJkID0gcmVxdWlyZSgnLi9ib2FyZCcpO1xyXG52YXIgdXRpbCA9IHJlcXVpcmUoJy4vdXRpbCcpO1xyXG52YXIgZHJhdyA9IHJlcXVpcmUoJy4vZHJhdycpO1xyXG5cclxudmFyIG9yaWdpblRhcmdldDtcclxuXHJcbmZ1bmN0aW9uIGhhc2hQaWVjZShwaWVjZSkge1xyXG4gIHJldHVybiBwaWVjZSA/IHBpZWNlLmNvbG9yICsgcGllY2Uucm9sZSA6ICcnO1xyXG59XHJcblxyXG5mdW5jdGlvbiBjb21wdXRlU3F1YXJlQm91bmRzKGRhdGEsIGJvdW5kcywga2V5KSB7XHJcbiAgdmFyIHBvcyA9IHV0aWwua2V5MnBvcyhrZXkpO1xyXG4gIGlmIChkYXRhLm9yaWVudGF0aW9uICE9PSAnd2hpdGUnKSB7XHJcbiAgICBwb3NbMF0gPSA5IC0gcG9zWzBdO1xyXG4gICAgcG9zWzFdID0gOSAtIHBvc1sxXTtcclxuICB9XHJcbiAgcmV0dXJuIHtcclxuICAgIGxlZnQ6IGJvdW5kcy5sZWZ0ICsgYm91bmRzLndpZHRoICogKHBvc1swXSAtIDEpIC8gOCxcclxuICAgIHRvcDogYm91bmRzLnRvcCArIGJvdW5kcy5oZWlnaHQgKiAoOCAtIHBvc1sxXSkgLyA4LFxyXG4gICAgd2lkdGg6IGJvdW5kcy53aWR0aCAvIDgsXHJcbiAgICBoZWlnaHQ6IGJvdW5kcy5oZWlnaHQgLyA4XHJcbiAgfTtcclxufVxyXG5cclxuZnVuY3Rpb24gc3RhcnQoZGF0YSwgZSkge1xyXG4gIGlmIChlLmJ1dHRvbiAhPT0gdW5kZWZpbmVkICYmIGUuYnV0dG9uICE9PSAwKSByZXR1cm47IC8vIG9ubHkgdG91Y2ggb3IgbGVmdCBjbGlja1xyXG4gIGlmIChlLnRvdWNoZXMgJiYgZS50b3VjaGVzLmxlbmd0aCA+IDEpIHJldHVybjsgLy8gc3VwcG9ydCBvbmUgZmluZ2VyIHRvdWNoIG9ubHlcclxuICBlLnN0b3BQcm9wYWdhdGlvbigpO1xyXG4gIGUucHJldmVudERlZmF1bHQoKTtcclxuICBvcmlnaW5UYXJnZXQgPSBlLnRhcmdldDtcclxuICB2YXIgcHJldmlvdXNseVNlbGVjdGVkID0gZGF0YS5zZWxlY3RlZDtcclxuICB2YXIgcG9zaXRpb24gPSB1dGlsLmV2ZW50UG9zaXRpb24oZSk7XHJcbiAgdmFyIGJvdW5kcyA9IGRhdGEuYm91bmRzKCk7XHJcbiAgdmFyIG9yaWcgPSBib2FyZC5nZXRLZXlBdERvbVBvcyhkYXRhLCBwb3NpdGlvbiwgYm91bmRzKTtcclxuICB2YXIgcGllY2UgPSBkYXRhLnBpZWNlc1tvcmlnXTtcclxuICBpZiAoIXByZXZpb3VzbHlTZWxlY3RlZCAmJiAoXHJcbiAgICBkYXRhLmRyYXdhYmxlLmVyYXNlT25DbGljayB8fFxyXG4gICAgKCFwaWVjZSB8fCBwaWVjZS5jb2xvciAhPT0gZGF0YS50dXJuQ29sb3IpXHJcbiAgKSkgZHJhdy5jbGVhcihkYXRhKTtcclxuICBpZiAoZGF0YS52aWV3T25seSkgcmV0dXJuO1xyXG4gIHZhciBoYWRQcmVtb3ZlID0gISFkYXRhLnByZW1vdmFibGUuY3VycmVudDtcclxuICB2YXIgaGFkUHJlZHJvcCA9ICEhZGF0YS5wcmVkcm9wcGFibGUuY3VycmVudC5rZXk7XHJcbiAgYm9hcmQuc2VsZWN0U3F1YXJlKGRhdGEsIG9yaWcpO1xyXG4gIHZhciBzdGlsbFNlbGVjdGVkID0gZGF0YS5zZWxlY3RlZCA9PT0gb3JpZztcclxuICBpZiAocGllY2UgJiYgc3RpbGxTZWxlY3RlZCAmJiBib2FyZC5pc0RyYWdnYWJsZShkYXRhLCBvcmlnKSkge1xyXG4gICAgdmFyIHNxdWFyZUJvdW5kcyA9IGNvbXB1dGVTcXVhcmVCb3VuZHMoZGF0YSwgYm91bmRzLCBvcmlnKTtcclxuICAgIGRhdGEuZHJhZ2dhYmxlLmN1cnJlbnQgPSB7XHJcbiAgICAgIHByZXZpb3VzbHlTZWxlY3RlZDogcHJldmlvdXNseVNlbGVjdGVkLFxyXG4gICAgICBvcmlnOiBvcmlnLFxyXG4gICAgICBwaWVjZTogaGFzaFBpZWNlKHBpZWNlKSxcclxuICAgICAgcmVsOiBwb3NpdGlvbixcclxuICAgICAgZXBvczogcG9zaXRpb24sXHJcbiAgICAgIHBvczogWzAsIDBdLFxyXG4gICAgICBkZWM6IGRhdGEuZHJhZ2dhYmxlLmNlbnRlclBpZWNlID8gW1xyXG4gICAgICAgIHBvc2l0aW9uWzBdIC0gKHNxdWFyZUJvdW5kcy5sZWZ0ICsgc3F1YXJlQm91bmRzLndpZHRoIC8gMiksXHJcbiAgICAgICAgcG9zaXRpb25bMV0gLSAoc3F1YXJlQm91bmRzLnRvcCArIHNxdWFyZUJvdW5kcy5oZWlnaHQgLyAyKVxyXG4gICAgICBdIDogWzAsIDBdLFxyXG4gICAgICBib3VuZHM6IGJvdW5kcyxcclxuICAgICAgc3RhcnRlZDogZGF0YS5kcmFnZ2FibGUuYXV0b0Rpc3RhbmNlICYmIGRhdGEuc3RhdHMuZHJhZ2dlZFxyXG4gICAgfTtcclxuICB9IGVsc2Uge1xyXG4gICAgaWYgKGhhZFByZW1vdmUpIGJvYXJkLnVuc2V0UHJlbW92ZShkYXRhKTtcclxuICAgIGlmIChoYWRQcmVkcm9wKSBib2FyZC51bnNldFByZWRyb3AoZGF0YSk7XHJcbiAgfVxyXG4gIHByb2Nlc3NEcmFnKGRhdGEpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBwcm9jZXNzRHJhZyhkYXRhKSB7XHJcbiAgdXRpbC5yZXF1ZXN0QW5pbWF0aW9uRnJhbWUoZnVuY3Rpb24oKSB7XHJcbiAgICB2YXIgY3VyID0gZGF0YS5kcmFnZ2FibGUuY3VycmVudDtcclxuICAgIGlmIChjdXIub3JpZykge1xyXG4gICAgICAvLyBjYW5jZWwgYW5pbWF0aW9ucyB3aGlsZSBkcmFnZ2luZ1xyXG4gICAgICBpZiAoZGF0YS5hbmltYXRpb24uY3VycmVudC5zdGFydCAmJiBkYXRhLmFuaW1hdGlvbi5jdXJyZW50LmFuaW1zW2N1ci5vcmlnXSlcclxuICAgICAgICBkYXRhLmFuaW1hdGlvbi5jdXJyZW50ID0ge307XHJcbiAgICAgIC8vIGlmIG1vdmluZyBwaWVjZSBpcyBnb25lLCBjYW5jZWxcclxuICAgICAgaWYgKGhhc2hQaWVjZShkYXRhLnBpZWNlc1tjdXIub3JpZ10pICE9PSBjdXIucGllY2UpIGNhbmNlbChkYXRhKTtcclxuICAgICAgZWxzZSB7XHJcbiAgICAgICAgaWYgKCFjdXIuc3RhcnRlZCAmJiB1dGlsLmRpc3RhbmNlKGN1ci5lcG9zLCBjdXIucmVsKSA+PSBkYXRhLmRyYWdnYWJsZS5kaXN0YW5jZSlcclxuICAgICAgICAgIGN1ci5zdGFydGVkID0gdHJ1ZTtcclxuICAgICAgICBpZiAoY3VyLnN0YXJ0ZWQpIHtcclxuICAgICAgICAgIGN1ci5wb3MgPSBbXHJcbiAgICAgICAgICAgIGN1ci5lcG9zWzBdIC0gY3VyLnJlbFswXSxcclxuICAgICAgICAgICAgY3VyLmVwb3NbMV0gLSBjdXIucmVsWzFdXHJcbiAgICAgICAgICBdO1xyXG4gICAgICAgICAgY3VyLm92ZXIgPSBib2FyZC5nZXRLZXlBdERvbVBvcyhkYXRhLCBjdXIuZXBvcywgY3VyLmJvdW5kcyk7XHJcbiAgICAgICAgfVxyXG4gICAgICB9XHJcbiAgICB9XHJcbiAgICBkYXRhLnJlbmRlcigpO1xyXG4gICAgaWYgKGN1ci5vcmlnKSBwcm9jZXNzRHJhZyhkYXRhKTtcclxuICB9KTtcclxufVxyXG5cclxuZnVuY3Rpb24gbW92ZShkYXRhLCBlKSB7XHJcbiAgaWYgKGUudG91Y2hlcyAmJiBlLnRvdWNoZXMubGVuZ3RoID4gMSkgcmV0dXJuOyAvLyBzdXBwb3J0IG9uZSBmaW5nZXIgdG91Y2ggb25seVxyXG4gIGlmIChkYXRhLmRyYWdnYWJsZS5jdXJyZW50Lm9yaWcpXHJcbiAgICBkYXRhLmRyYWdnYWJsZS5jdXJyZW50LmVwb3MgPSB1dGlsLmV2ZW50UG9zaXRpb24oZSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGVuZChkYXRhLCBlKSB7XHJcbiAgdmFyIGN1ciA9IGRhdGEuZHJhZ2dhYmxlLmN1cnJlbnQ7XHJcbiAgdmFyIG9yaWcgPSBjdXIgPyBjdXIub3JpZyA6IG51bGw7XHJcbiAgaWYgKCFvcmlnKSByZXR1cm47XHJcbiAgLy8gY29tcGFyaW5nIHdpdGggdGhlIG9yaWdpbiB0YXJnZXQgaXMgYW4gZWFzeSB3YXkgdG8gdGVzdCB0aGF0IHRoZSBlbmQgZXZlbnRcclxuICAvLyBoYXMgdGhlIHNhbWUgdG91Y2ggb3JpZ2luXHJcbiAgaWYgKGUudHlwZSA9PT0gXCJ0b3VjaGVuZFwiICYmIG9yaWdpblRhcmdldCAhPT0gZS50YXJnZXQgJiYgIWN1ci5uZXdQaWVjZSkge1xyXG4gICAgZGF0YS5kcmFnZ2FibGUuY3VycmVudCA9IHt9O1xyXG4gICAgcmV0dXJuO1xyXG4gIH1cclxuICBib2FyZC51bnNldFByZW1vdmUoZGF0YSk7XHJcbiAgYm9hcmQudW5zZXRQcmVkcm9wKGRhdGEpO1xyXG4gIHZhciBldmVudFBvcyA9IHV0aWwuZXZlbnRQb3NpdGlvbihlKVxyXG4gIHZhciBkZXN0ID0gZXZlbnRQb3MgPyBib2FyZC5nZXRLZXlBdERvbVBvcyhkYXRhLCBldmVudFBvcywgY3VyLmJvdW5kcykgOiBjdXIub3ZlcjtcclxuICBpZiAoY3VyLnN0YXJ0ZWQpIHtcclxuICAgIGlmIChjdXIubmV3UGllY2UpIGJvYXJkLmRyb3BOZXdQaWVjZShkYXRhLCBvcmlnLCBkZXN0KTtcclxuICAgIGVsc2Uge1xyXG4gICAgICBpZiAob3JpZyAhPT0gZGVzdCkgZGF0YS5tb3ZhYmxlLmRyb3BwZWQgPSBbb3JpZywgZGVzdF07XHJcbiAgICAgIGlmIChib2FyZC51c2VyTW92ZShkYXRhLCBvcmlnLCBkZXN0KSkgZGF0YS5zdGF0cy5kcmFnZ2VkID0gdHJ1ZTtcclxuICAgIH1cclxuICB9XHJcbiAgaWYgKG9yaWcgPT09IGN1ci5wcmV2aW91c2x5U2VsZWN0ZWQgJiYgKG9yaWcgPT09IGRlc3QgfHwgIWRlc3QpKVxyXG4gICAgYm9hcmQuc2V0U2VsZWN0ZWQoZGF0YSwgbnVsbCk7XHJcbiAgZWxzZSBpZiAoIWRhdGEuc2VsZWN0YWJsZS5lbmFibGVkKSBib2FyZC5zZXRTZWxlY3RlZChkYXRhLCBudWxsKTtcclxuICBkYXRhLmRyYWdnYWJsZS5jdXJyZW50ID0ge307XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGNhbmNlbChkYXRhKSB7XHJcbiAgaWYgKGRhdGEuZHJhZ2dhYmxlLmN1cnJlbnQub3JpZykge1xyXG4gICAgZGF0YS5kcmFnZ2FibGUuY3VycmVudCA9IHt9O1xyXG4gICAgYm9hcmQuc2VsZWN0U3F1YXJlKGRhdGEsIG51bGwpO1xyXG4gIH1cclxufVxyXG5cclxubW9kdWxlLmV4cG9ydHMgPSB7XHJcbiAgc3RhcnQ6IHN0YXJ0LFxyXG4gIG1vdmU6IG1vdmUsXHJcbiAgZW5kOiBlbmQsXHJcbiAgY2FuY2VsOiBjYW5jZWwsXHJcbiAgcHJvY2Vzc0RyYWc6IHByb2Nlc3NEcmFnIC8vIG11c3QgYmUgZXhwb3NlZCBmb3IgYm9hcmQgZWRpdG9yc1xyXG59O1xyXG4iLCJ2YXIgYm9hcmQgPSByZXF1aXJlKCcuL2JvYXJkJyk7XHJcbnZhciB1dGlsID0gcmVxdWlyZSgnLi91dGlsJyk7XHJcblxyXG52YXIgYnJ1c2hlcyA9IFsnZ3JlZW4nLCAncmVkJywgJ2JsdWUnLCAneWVsbG93J107XHJcblxyXG5mdW5jdGlvbiBoYXNoUGllY2UocGllY2UpIHtcclxuICByZXR1cm4gcGllY2UgPyBwaWVjZS5jb2xvciArICcgJyArIHBpZWNlLnJvbGUgOiAnJztcclxufVxyXG5cclxuZnVuY3Rpb24gc3RhcnQoZGF0YSwgZSkge1xyXG4gIGlmIChlLnRvdWNoZXMgJiYgZS50b3VjaGVzLmxlbmd0aCA+IDEpIHJldHVybjsgLy8gc3VwcG9ydCBvbmUgZmluZ2VyIHRvdWNoIG9ubHlcclxuICBlLnN0b3BQcm9wYWdhdGlvbigpO1xyXG4gIGUucHJldmVudERlZmF1bHQoKTtcclxuICBib2FyZC5jYW5jZWxNb3ZlKGRhdGEpO1xyXG4gIHZhciBwb3NpdGlvbiA9IHV0aWwuZXZlbnRQb3NpdGlvbihlKTtcclxuICB2YXIgYm91bmRzID0gZGF0YS5ib3VuZHMoKTtcclxuICB2YXIgb3JpZyA9IGJvYXJkLmdldEtleUF0RG9tUG9zKGRhdGEsIHBvc2l0aW9uLCBib3VuZHMpO1xyXG4gIGRhdGEuZHJhd2FibGUuY3VycmVudCA9IHtcclxuICAgIG9yaWc6IG9yaWcsXHJcbiAgICBlcG9zOiBwb3NpdGlvbixcclxuICAgIGJvdW5kczogYm91bmRzLFxyXG4gICAgYnJ1c2g6IGJydXNoZXNbKGUuc2hpZnRLZXkgJiB1dGlsLmlzUmlnaHRCdXR0b24oZSkpICsgKGUuYWx0S2V5ID8gMiA6IDApXVxyXG4gIH07XHJcbiAgcHJvY2Vzc0RyYXcoZGF0YSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHByb2Nlc3NEcmF3KGRhdGEpIHtcclxuICB1dGlsLnJlcXVlc3RBbmltYXRpb25GcmFtZShmdW5jdGlvbigpIHtcclxuICAgIHZhciBjdXIgPSBkYXRhLmRyYXdhYmxlLmN1cnJlbnQ7XHJcbiAgICBpZiAoY3VyLm9yaWcpIHtcclxuICAgICAgdmFyIGRlc3QgPSBib2FyZC5nZXRLZXlBdERvbVBvcyhkYXRhLCBjdXIuZXBvcywgY3VyLmJvdW5kcyk7XHJcbiAgICAgIGlmIChjdXIub3JpZyA9PT0gZGVzdCkgY3VyLmRlc3QgPSB1bmRlZmluZWQ7XHJcbiAgICAgIGVsc2UgY3VyLmRlc3QgPSBkZXN0O1xyXG4gICAgfVxyXG4gICAgZGF0YS5yZW5kZXIoKTtcclxuICAgIGlmIChjdXIub3JpZykgcHJvY2Vzc0RyYXcoZGF0YSk7XHJcbiAgfSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIG1vdmUoZGF0YSwgZSkge1xyXG4gIGlmIChkYXRhLmRyYXdhYmxlLmN1cnJlbnQub3JpZylcclxuICAgIGRhdGEuZHJhd2FibGUuY3VycmVudC5lcG9zID0gdXRpbC5ldmVudFBvc2l0aW9uKGUpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBlbmQoZGF0YSwgZSkge1xyXG4gIHZhciBkcmF3YWJsZSA9IGRhdGEuZHJhd2FibGU7XHJcbiAgdmFyIG9yaWcgPSBkcmF3YWJsZS5jdXJyZW50Lm9yaWc7XHJcbiAgdmFyIGRlc3QgPSBkcmF3YWJsZS5jdXJyZW50LmRlc3Q7XHJcbiAgaWYgKG9yaWcgJiYgZGVzdCkgYWRkTGluZShkcmF3YWJsZSwgb3JpZywgZGVzdCk7XHJcbiAgZWxzZSBpZiAob3JpZykgYWRkQ2lyY2xlKGRyYXdhYmxlLCBvcmlnKTtcclxuICBkcmF3YWJsZS5jdXJyZW50ID0ge307XHJcbiAgZGF0YS5yZW5kZXIoKTtcclxufVxyXG5cclxuZnVuY3Rpb24gY2FuY2VsKGRhdGEpIHtcclxuICBpZiAoZGF0YS5kcmF3YWJsZS5jdXJyZW50Lm9yaWcpIGRhdGEuZHJhd2FibGUuY3VycmVudCA9IHt9O1xyXG59XHJcblxyXG5mdW5jdGlvbiBjbGVhcihkYXRhKSB7XHJcbiAgaWYgKGRhdGEuZHJhd2FibGUuc2hhcGVzLmxlbmd0aCkge1xyXG4gICAgZGF0YS5kcmF3YWJsZS5zaGFwZXMgPSBbXTtcclxuICAgIGRhdGEucmVuZGVyKCk7XHJcbiAgICBvbkNoYW5nZShkYXRhLmRyYXdhYmxlKTtcclxuICB9XHJcbn1cclxuXHJcbmZ1bmN0aW9uIG5vdChmKSB7XHJcbiAgcmV0dXJuIGZ1bmN0aW9uKHgpIHtcclxuICAgIHJldHVybiAhZih4KTtcclxuICB9O1xyXG59XHJcblxyXG5mdW5jdGlvbiBhZGRDaXJjbGUoZHJhd2FibGUsIGtleSkge1xyXG4gIHZhciBicnVzaCA9IGRyYXdhYmxlLmN1cnJlbnQuYnJ1c2g7XHJcbiAgdmFyIHNhbWVDaXJjbGUgPSBmdW5jdGlvbihzKSB7XHJcbiAgICByZXR1cm4gcy5vcmlnID09PSBrZXkgJiYgIXMuZGVzdDtcclxuICB9O1xyXG4gIHZhciBzaW1pbGFyID0gZHJhd2FibGUuc2hhcGVzLmZpbHRlcihzYW1lQ2lyY2xlKVswXTtcclxuICBpZiAoc2ltaWxhcikgZHJhd2FibGUuc2hhcGVzID0gZHJhd2FibGUuc2hhcGVzLmZpbHRlcihub3Qoc2FtZUNpcmNsZSkpO1xyXG4gIGlmICghc2ltaWxhciB8fCBzaW1pbGFyLmJydXNoICE9PSBicnVzaCkgZHJhd2FibGUuc2hhcGVzLnB1c2goe1xyXG4gICAgYnJ1c2g6IGJydXNoLFxyXG4gICAgb3JpZzoga2V5XHJcbiAgfSk7XHJcbiAgb25DaGFuZ2UoZHJhd2FibGUpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBhZGRMaW5lKGRyYXdhYmxlLCBvcmlnLCBkZXN0KSB7XHJcbiAgdmFyIGJydXNoID0gZHJhd2FibGUuY3VycmVudC5icnVzaDtcclxuICB2YXIgc2FtZUxpbmUgPSBmdW5jdGlvbihzKSB7XHJcbiAgICByZXR1cm4gcy5vcmlnICYmIHMuZGVzdCAmJiAoXHJcbiAgICAgIChzLm9yaWcgPT09IG9yaWcgJiYgcy5kZXN0ID09PSBkZXN0KSB8fFxyXG4gICAgICAocy5kZXN0ID09PSBvcmlnICYmIHMub3JpZyA9PT0gZGVzdClcclxuICAgICk7XHJcbiAgfTtcclxuICB2YXIgZXhpc3RzID0gZHJhd2FibGUuc2hhcGVzLmZpbHRlcihzYW1lTGluZSkubGVuZ3RoID4gMDtcclxuICBpZiAoZXhpc3RzKSBkcmF3YWJsZS5zaGFwZXMgPSBkcmF3YWJsZS5zaGFwZXMuZmlsdGVyKG5vdChzYW1lTGluZSkpO1xyXG4gIGVsc2UgZHJhd2FibGUuc2hhcGVzLnB1c2goe1xyXG4gICAgYnJ1c2g6IGJydXNoLFxyXG4gICAgb3JpZzogb3JpZyxcclxuICAgIGRlc3Q6IGRlc3RcclxuICB9KTtcclxuICBvbkNoYW5nZShkcmF3YWJsZSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIG9uQ2hhbmdlKGRyYXdhYmxlKSB7XHJcbiAgZHJhd2FibGUub25DaGFuZ2UoZHJhd2FibGUuc2hhcGVzKTtcclxufVxyXG5cclxubW9kdWxlLmV4cG9ydHMgPSB7XHJcbiAgc3RhcnQ6IHN0YXJ0LFxyXG4gIG1vdmU6IG1vdmUsXHJcbiAgZW5kOiBlbmQsXHJcbiAgY2FuY2VsOiBjYW5jZWwsXHJcbiAgY2xlYXI6IGNsZWFyLFxyXG4gIHByb2Nlc3NEcmF3OiBwcm9jZXNzRHJhd1xyXG59O1xyXG4iLCJ2YXIgdXRpbCA9IHJlcXVpcmUoJy4vdXRpbCcpO1xyXG5cclxudmFyIGluaXRpYWwgPSAncm5icWtibnIvcHBwcHBwcHAvOC84LzgvOC9QUFBQUFBQUC9STkJRS0JOUic7XHJcblxyXG52YXIgcm9sZXMgPSB7XHJcbiAgcDogXCJwYXduXCIsXHJcbiAgcjogXCJyb29rXCIsXHJcbiAgbjogXCJrbmlnaHRcIixcclxuICBiOiBcImJpc2hvcFwiLFxyXG4gIHE6IFwicXVlZW5cIixcclxuICBrOiBcImtpbmdcIlxyXG59O1xyXG5cclxudmFyIGxldHRlcnMgPSB7XHJcbiAgcGF3bjogXCJwXCIsXHJcbiAgcm9vazogXCJyXCIsXHJcbiAga25pZ2h0OiBcIm5cIixcclxuICBiaXNob3A6IFwiYlwiLFxyXG4gIHF1ZWVuOiBcInFcIixcclxuICBraW5nOiBcImtcIlxyXG59O1xyXG5cclxuZnVuY3Rpb24gcmVhZChmZW4pIHtcclxuICBpZiAoZmVuID09PSAnc3RhcnQnKSBmZW4gPSBpbml0aWFsO1xyXG4gIHZhciBwaWVjZXMgPSB7fTtcclxuICBmZW4ucmVwbGFjZSgvIC4rJC8sICcnKS5yZXBsYWNlKC9+L2csICcnKS5zcGxpdCgnLycpLmZvckVhY2goZnVuY3Rpb24ocm93LCB5KSB7XHJcbiAgICB2YXIgeCA9IDA7XHJcbiAgICByb3cuc3BsaXQoJycpLmZvckVhY2goZnVuY3Rpb24odikge1xyXG4gICAgICB2YXIgbmIgPSBwYXJzZUludCh2KTtcclxuICAgICAgaWYgKG5iKSB4ICs9IG5iO1xyXG4gICAgICBlbHNlIHtcclxuICAgICAgICB4Kys7XHJcbiAgICAgICAgcGllY2VzW3V0aWwucG9zMmtleShbeCwgOCAtIHldKV0gPSB7XHJcbiAgICAgICAgICByb2xlOiByb2xlc1t2LnRvTG93ZXJDYXNlKCldLFxyXG4gICAgICAgICAgY29sb3I6IHYgPT09IHYudG9Mb3dlckNhc2UoKSA/ICdibGFjaycgOiAnd2hpdGUnXHJcbiAgICAgICAgfTtcclxuICAgICAgfVxyXG4gICAgfSk7XHJcbiAgfSk7XHJcblxyXG4gIHJldHVybiBwaWVjZXM7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHdyaXRlKHBpZWNlcykge1xyXG4gIHJldHVybiBbOCwgNywgNiwgNSwgNCwgMywgMl0ucmVkdWNlKFxyXG4gICAgZnVuY3Rpb24oc3RyLCBuYikge1xyXG4gICAgICByZXR1cm4gc3RyLnJlcGxhY2UobmV3IFJlZ0V4cChBcnJheShuYiArIDEpLmpvaW4oJzEnKSwgJ2cnKSwgbmIpO1xyXG4gICAgfSxcclxuICAgIHV0aWwuaW52UmFua3MubWFwKGZ1bmN0aW9uKHkpIHtcclxuICAgICAgcmV0dXJuIHV0aWwucmFua3MubWFwKGZ1bmN0aW9uKHgpIHtcclxuICAgICAgICB2YXIgcGllY2UgPSBwaWVjZXNbdXRpbC5wb3Mya2V5KFt4LCB5XSldO1xyXG4gICAgICAgIGlmIChwaWVjZSkge1xyXG4gICAgICAgICAgdmFyIGxldHRlciA9IGxldHRlcnNbcGllY2Uucm9sZV07XHJcbiAgICAgICAgICByZXR1cm4gcGllY2UuY29sb3IgPT09ICd3aGl0ZScgPyBsZXR0ZXIudG9VcHBlckNhc2UoKSA6IGxldHRlcjtcclxuICAgICAgICB9IGVsc2UgcmV0dXJuICcxJztcclxuICAgICAgfSkuam9pbignJyk7XHJcbiAgICB9KS5qb2luKCcvJykpO1xyXG59XHJcblxyXG5tb2R1bGUuZXhwb3J0cyA9IHtcclxuICBpbml0aWFsOiBpbml0aWFsLFxyXG4gIHJlYWQ6IHJlYWQsXHJcbiAgd3JpdGU6IHdyaXRlXHJcbn07XHJcbiIsInZhciBzdGFydEF0O1xyXG5cclxudmFyIHN0YXJ0ID0gZnVuY3Rpb24oKSB7XHJcbiAgc3RhcnRBdCA9IG5ldyBEYXRlKCk7XHJcbn07XHJcblxyXG52YXIgY2FuY2VsID0gZnVuY3Rpb24oKSB7XHJcbiAgc3RhcnRBdCA9IG51bGw7XHJcbn07XHJcblxyXG52YXIgc3RvcCA9IGZ1bmN0aW9uKCkge1xyXG4gIGlmICghc3RhcnRBdCkgcmV0dXJuIDA7XHJcbiAgdmFyIHRpbWUgPSBuZXcgRGF0ZSgpIC0gc3RhcnRBdDtcclxuICBzdGFydEF0ID0gbnVsbDtcclxuICByZXR1cm4gdGltZTtcclxufTtcclxuXHJcbm1vZHVsZS5leHBvcnRzID0ge1xyXG4gIHN0YXJ0OiBzdGFydCxcclxuICBjYW5jZWw6IGNhbmNlbCxcclxuICBzdG9wOiBzdG9wXHJcbn07XHJcbiIsInZhciB1dGlsID0gcmVxdWlyZSgnLi91dGlsJyk7XHJcblxyXG5mdW5jdGlvbiBkaWZmKGEsIGIpIHtcclxuICByZXR1cm4gTWF0aC5hYnMoYSAtIGIpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBwYXduKGNvbG9yLCB4MSwgeTEsIHgyLCB5Mikge1xyXG4gIHJldHVybiBkaWZmKHgxLCB4MikgPCAyICYmIChcclxuICAgIGNvbG9yID09PSAnd2hpdGUnID8gKFxyXG4gICAgICAvLyBhbGxvdyAyIHNxdWFyZXMgZnJvbSAxIGFuZCA4LCBmb3IgaG9yZGVcclxuICAgICAgeTIgPT09IHkxICsgMSB8fCAoeTEgPD0gMiAmJiB5MiA9PT0gKHkxICsgMikgJiYgeDEgPT09IHgyKVxyXG4gICAgKSA6IChcclxuICAgICAgeTIgPT09IHkxIC0gMSB8fCAoeTEgPj0gNyAmJiB5MiA9PT0gKHkxIC0gMikgJiYgeDEgPT09IHgyKVxyXG4gICAgKVxyXG4gICk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGtuaWdodCh4MSwgeTEsIHgyLCB5Mikge1xyXG4gIHZhciB4ZCA9IGRpZmYoeDEsIHgyKTtcclxuICB2YXIgeWQgPSBkaWZmKHkxLCB5Mik7XHJcbiAgcmV0dXJuICh4ZCA9PT0gMSAmJiB5ZCA9PT0gMikgfHwgKHhkID09PSAyICYmIHlkID09PSAxKTtcclxufVxyXG5cclxuZnVuY3Rpb24gYmlzaG9wKHgxLCB5MSwgeDIsIHkyKSB7XHJcbiAgcmV0dXJuIGRpZmYoeDEsIHgyKSA9PT0gZGlmZih5MSwgeTIpO1xyXG59XHJcblxyXG5mdW5jdGlvbiByb29rKHgxLCB5MSwgeDIsIHkyKSB7XHJcbiAgcmV0dXJuIHgxID09PSB4MiB8fCB5MSA9PT0geTI7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHF1ZWVuKHgxLCB5MSwgeDIsIHkyKSB7XHJcbiAgcmV0dXJuIGJpc2hvcCh4MSwgeTEsIHgyLCB5MikgfHwgcm9vayh4MSwgeTEsIHgyLCB5Mik7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGtpbmcoY29sb3IsIHJvb2tGaWxlcywgY2FuQ2FzdGxlLCB4MSwgeTEsIHgyLCB5Mikge1xyXG4gIHJldHVybiAoXHJcbiAgICBkaWZmKHgxLCB4MikgPCAyICYmIGRpZmYoeTEsIHkyKSA8IDJcclxuICApIHx8IChcclxuICAgIGNhbkNhc3RsZSAmJiB5MSA9PT0geTIgJiYgeTEgPT09IChjb2xvciA9PT0gJ3doaXRlJyA/IDEgOiA4KSAmJiAoXHJcbiAgICAgICh4MSA9PT0gNSAmJiAoeDIgPT09IDMgfHwgeDIgPT09IDcpKSB8fCB1dGlsLmNvbnRhaW5zWChyb29rRmlsZXMsIHgyKVxyXG4gICAgKVxyXG4gICk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHJvb2tGaWxlc09mKHBpZWNlcywgY29sb3IpIHtcclxuICByZXR1cm4gT2JqZWN0LmtleXMocGllY2VzKS5maWx0ZXIoZnVuY3Rpb24oa2V5KSB7XHJcbiAgICB2YXIgcGllY2UgPSBwaWVjZXNba2V5XTtcclxuICAgIHJldHVybiBwaWVjZSAmJiBwaWVjZS5jb2xvciA9PT0gY29sb3IgJiYgcGllY2Uucm9sZSA9PT0gJ3Jvb2snO1xyXG4gIH0pLm1hcChmdW5jdGlvbihrZXkpIHtcclxuICAgIHJldHVybiB1dGlsLmtleTJwb3Moa2V5KVswXTtcclxuICB9KTtcclxufVxyXG5cclxuZnVuY3Rpb24gY29tcHV0ZShwaWVjZXMsIGtleSwgY2FuQ2FzdGxlKSB7XHJcbiAgdmFyIHBpZWNlID0gcGllY2VzW2tleV07XHJcbiAgdmFyIHBvcyA9IHV0aWwua2V5MnBvcyhrZXkpO1xyXG4gIHZhciBtb2JpbGl0eTtcclxuICBzd2l0Y2ggKHBpZWNlLnJvbGUpIHtcclxuICAgIGNhc2UgJ3Bhd24nOlxyXG4gICAgICBtb2JpbGl0eSA9IHBhd24uYmluZChudWxsLCBwaWVjZS5jb2xvcik7XHJcbiAgICAgIGJyZWFrO1xyXG4gICAgY2FzZSAna25pZ2h0JzpcclxuICAgICAgbW9iaWxpdHkgPSBrbmlnaHQ7XHJcbiAgICAgIGJyZWFrO1xyXG4gICAgY2FzZSAnYmlzaG9wJzpcclxuICAgICAgbW9iaWxpdHkgPSBiaXNob3A7XHJcbiAgICAgIGJyZWFrO1xyXG4gICAgY2FzZSAncm9vayc6XHJcbiAgICAgIG1vYmlsaXR5ID0gcm9vaztcclxuICAgICAgYnJlYWs7XHJcbiAgICBjYXNlICdxdWVlbic6XHJcbiAgICAgIG1vYmlsaXR5ID0gcXVlZW47XHJcbiAgICAgIGJyZWFrO1xyXG4gICAgY2FzZSAna2luZyc6XHJcbiAgICAgIG1vYmlsaXR5ID0ga2luZy5iaW5kKG51bGwsIHBpZWNlLmNvbG9yLCByb29rRmlsZXNPZihwaWVjZXMsIHBpZWNlLmNvbG9yKSwgY2FuQ2FzdGxlKTtcclxuICAgICAgYnJlYWs7XHJcbiAgfVxyXG4gIHJldHVybiB1dGlsLmFsbFBvcy5maWx0ZXIoZnVuY3Rpb24ocG9zMikge1xyXG4gICAgcmV0dXJuIChwb3NbMF0gIT09IHBvczJbMF0gfHwgcG9zWzFdICE9PSBwb3MyWzFdKSAmJiBtb2JpbGl0eShwb3NbMF0sIHBvc1sxXSwgcG9zMlswXSwgcG9zMlsxXSk7XHJcbiAgfSkubWFwKHV0aWwucG9zMmtleSk7XHJcbn1cclxuXHJcbm1vZHVsZS5leHBvcnRzID0gY29tcHV0ZTtcclxuIiwidmFyIG0gPSByZXF1aXJlKCdtaXRocmlsJyk7XHJcbnZhciBrZXkycG9zID0gcmVxdWlyZSgnLi91dGlsJykua2V5MnBvcztcclxudmFyIGlzVHJpZGVudCA9IHJlcXVpcmUoJy4vdXRpbCcpLmlzVHJpZGVudDtcclxuXHJcbmZ1bmN0aW9uIGNpcmNsZVdpZHRoKGN1cnJlbnQsIGJvdW5kcykge1xyXG4gIHJldHVybiAoY3VycmVudCA/IDIgOiA0KSAvIDUxMiAqIGJvdW5kcy53aWR0aDtcclxufVxyXG5cclxuZnVuY3Rpb24gbGluZVdpZHRoKGJydXNoLCBjdXJyZW50LCBib3VuZHMpIHtcclxuICByZXR1cm4gKGJydXNoLmxpbmVXaWR0aCB8fCAxMCkgKiAoY3VycmVudCA/IDAuNyA6IDEpIC8gNTEyICogYm91bmRzLndpZHRoO1xyXG59XHJcblxyXG5mdW5jdGlvbiBvcGFjaXR5KGJydXNoLCBjdXJyZW50KSB7XHJcbiAgcmV0dXJuIChicnVzaC5vcGFjaXR5IHx8IDEpICogKGN1cnJlbnQgPyAwLjYgOiAxKTtcclxufVxyXG5cclxuZnVuY3Rpb24gYXJyb3dNYXJnaW4oY3VycmVudCwgYm91bmRzKSB7XHJcbiAgcmV0dXJuIGlzVHJpZGVudCgpID8gMCA6ICgoY3VycmVudCA/IDEwIDogMjApIC8gNTEyICogYm91bmRzLndpZHRoKTtcclxufVxyXG5cclxuZnVuY3Rpb24gcG9zMnB4KHBvcywgYm91bmRzKSB7XHJcbiAgdmFyIHNxdWFyZVNpemUgPSBib3VuZHMud2lkdGggLyA4O1xyXG4gIHJldHVybiBbKHBvc1swXSAtIDAuNSkgKiBzcXVhcmVTaXplLCAoOC41IC0gcG9zWzFdKSAqIHNxdWFyZVNpemVdO1xyXG59XHJcblxyXG5mdW5jdGlvbiBjaXJjbGUoYnJ1c2gsIHBvcywgY3VycmVudCwgYm91bmRzKSB7XHJcbiAgdmFyIG8gPSBwb3MycHgocG9zLCBib3VuZHMpO1xyXG4gIHZhciB3aWR0aCA9IGNpcmNsZVdpZHRoKGN1cnJlbnQsIGJvdW5kcyk7XHJcbiAgdmFyIHJhZGl1cyA9IGJvdW5kcy53aWR0aCAvIDE2O1xyXG4gIHJldHVybiB7XHJcbiAgICB0YWc6ICdjaXJjbGUnLFxyXG4gICAgYXR0cnM6IHtcclxuICAgICAga2V5OiBjdXJyZW50ID8gJ2N1cnJlbnQnIDogcG9zICsgYnJ1c2gua2V5LFxyXG4gICAgICBzdHJva2U6IGJydXNoLmNvbG9yLFxyXG4gICAgICAnc3Ryb2tlLXdpZHRoJzogd2lkdGgsXHJcbiAgICAgIGZpbGw6ICdub25lJyxcclxuICAgICAgb3BhY2l0eTogb3BhY2l0eShicnVzaCwgY3VycmVudCksXHJcbiAgICAgIGN4OiBvWzBdLFxyXG4gICAgICBjeTogb1sxXSxcclxuICAgICAgcjogcmFkaXVzIC0gd2lkdGggLyAyXHJcbiAgICB9XHJcbiAgfTtcclxufVxyXG5cclxuZnVuY3Rpb24gYXJyb3coYnJ1c2gsIG9yaWcsIGRlc3QsIGN1cnJlbnQsIGJvdW5kcykge1xyXG4gIHZhciBtID0gYXJyb3dNYXJnaW4oY3VycmVudCwgYm91bmRzKTtcclxuICB2YXIgYSA9IHBvczJweChvcmlnLCBib3VuZHMpO1xyXG4gIHZhciBiID0gcG9zMnB4KGRlc3QsIGJvdW5kcyk7XHJcbiAgdmFyIGR4ID0gYlswXSAtIGFbMF0sXHJcbiAgICBkeSA9IGJbMV0gLSBhWzFdLFxyXG4gICAgYW5nbGUgPSBNYXRoLmF0YW4yKGR5LCBkeCk7XHJcbiAgdmFyIHhvID0gTWF0aC5jb3MoYW5nbGUpICogbSxcclxuICAgIHlvID0gTWF0aC5zaW4oYW5nbGUpICogbTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiAnbGluZScsXHJcbiAgICBhdHRyczoge1xyXG4gICAgICBrZXk6IGN1cnJlbnQgPyAnY3VycmVudCcgOiBvcmlnICsgZGVzdCArIGJydXNoLmtleSxcclxuICAgICAgc3Ryb2tlOiBicnVzaC5jb2xvcixcclxuICAgICAgJ3N0cm9rZS13aWR0aCc6IGxpbmVXaWR0aChicnVzaCwgY3VycmVudCwgYm91bmRzKSxcclxuICAgICAgJ3N0cm9rZS1saW5lY2FwJzogJ3JvdW5kJyxcclxuICAgICAgJ21hcmtlci1lbmQnOiBpc1RyaWRlbnQoKSA/IG51bGwgOiAndXJsKCNhcnJvd2hlYWQtJyArIGJydXNoLmtleSArICcpJyxcclxuICAgICAgb3BhY2l0eTogb3BhY2l0eShicnVzaCwgY3VycmVudCksXHJcbiAgICAgIHgxOiBhWzBdLFxyXG4gICAgICB5MTogYVsxXSxcclxuICAgICAgeDI6IGJbMF0gLSB4byxcclxuICAgICAgeTI6IGJbMV0gLSB5b1xyXG4gICAgfVxyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHBpZWNlKGNmZywgcG9zLCBwaWVjZSwgYm91bmRzKSB7XHJcbiAgdmFyIG8gPSBwb3MycHgocG9zLCBib3VuZHMpO1xyXG4gIHZhciBzaXplID0gYm91bmRzLndpZHRoIC8gOCAqIChwaWVjZS5zY2FsZSB8fCAxKTtcclxuICB2YXIgbmFtZSA9IHBpZWNlLmNvbG9yID09PSAnd2hpdGUnID8gJ3cnIDogJ2InO1xyXG4gIG5hbWUgKz0gKHBpZWNlLnJvbGUgPT09ICdrbmlnaHQnID8gJ24nIDogcGllY2Uucm9sZVswXSkudG9VcHBlckNhc2UoKTtcclxuICB2YXIgaHJlZiA9IGNmZy5iYXNlVXJsICsgbmFtZSArICcuc3ZnJztcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiAnaW1hZ2UnLFxyXG4gICAgYXR0cnM6IHtcclxuICAgICAgY2xhc3M6IHBpZWNlLmNvbG9yICsgJyAnICsgcGllY2Uucm9sZSxcclxuICAgICAgeDogb1swXSAtIHNpemUgLyAyLFxyXG4gICAgICB5OiBvWzFdIC0gc2l6ZSAvIDIsXHJcbiAgICAgIHdpZHRoOiBzaXplLFxyXG4gICAgICBoZWlnaHQ6IHNpemUsXHJcbiAgICAgIGhyZWY6IGhyZWZcclxuICAgIH1cclxuICB9O1xyXG59XHJcblxyXG5mdW5jdGlvbiBkZWZzKGJydXNoZXMpIHtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiAnZGVmcycsXHJcbiAgICBjaGlsZHJlbjogW1xyXG4gICAgICBicnVzaGVzLm1hcChmdW5jdGlvbihicnVzaCkge1xyXG4gICAgICAgIHJldHVybiB7XHJcbiAgICAgICAgICBrZXk6IGJydXNoLmtleSxcclxuICAgICAgICAgIHRhZzogJ21hcmtlcicsXHJcbiAgICAgICAgICBhdHRyczoge1xyXG4gICAgICAgICAgICBpZDogJ2Fycm93aGVhZC0nICsgYnJ1c2gua2V5LFxyXG4gICAgICAgICAgICBvcmllbnQ6ICdhdXRvJyxcclxuICAgICAgICAgICAgbWFya2VyV2lkdGg6IDQsXHJcbiAgICAgICAgICAgIG1hcmtlckhlaWdodDogOCxcclxuICAgICAgICAgICAgcmVmWDogMi4wNSxcclxuICAgICAgICAgICAgcmVmWTogMi4wMVxyXG4gICAgICAgICAgfSxcclxuICAgICAgICAgIGNoaWxkcmVuOiBbe1xyXG4gICAgICAgICAgICB0YWc6ICdwYXRoJyxcclxuICAgICAgICAgICAgYXR0cnM6IHtcclxuICAgICAgICAgICAgICBkOiAnTTAsMCBWNCBMMywyIFonLFxyXG4gICAgICAgICAgICAgIGZpbGw6IGJydXNoLmNvbG9yXHJcbiAgICAgICAgICAgIH1cclxuICAgICAgICAgIH1dXHJcbiAgICAgICAgfVxyXG4gICAgICB9KVxyXG4gICAgXVxyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIG9yaWVudChwb3MsIGNvbG9yKSB7XHJcbiAgcmV0dXJuIGNvbG9yID09PSAnd2hpdGUnID8gcG9zIDogWzkgLSBwb3NbMF0sIDkgLSBwb3NbMV1dO1xyXG59XHJcblxyXG5mdW5jdGlvbiByZW5kZXJTaGFwZShkYXRhLCBjdXJyZW50LCBib3VuZHMpIHtcclxuICByZXR1cm4gZnVuY3Rpb24oc2hhcGUpIHtcclxuICAgIGlmIChzaGFwZS5vcmlnICYmIHNoYXBlLmRlc3QpIHJldHVybiBhcnJvdyhcclxuICAgICAgZGF0YS5kcmF3YWJsZS5icnVzaGVzW3NoYXBlLmJydXNoXSxcclxuICAgICAgb3JpZW50KGtleTJwb3Moc2hhcGUub3JpZyksIGRhdGEub3JpZW50YXRpb24pLFxyXG4gICAgICBvcmllbnQoa2V5MnBvcyhzaGFwZS5kZXN0KSwgZGF0YS5vcmllbnRhdGlvbiksXHJcbiAgICAgIGN1cnJlbnQsIGJvdW5kcyk7XHJcbiAgICBlbHNlIGlmIChzaGFwZS5waWVjZSkgcmV0dXJuIHBpZWNlKFxyXG4gICAgICBkYXRhLmRyYXdhYmxlLnBpZWNlcyxcclxuICAgICAgb3JpZW50KGtleTJwb3Moc2hhcGUub3JpZyksIGRhdGEub3JpZW50YXRpb24pLFxyXG4gICAgICBzaGFwZS5waWVjZSxcclxuICAgICAgYm91bmRzKTtcclxuICAgIGVsc2UgaWYgKHNoYXBlLm9yaWcpIHJldHVybiBjaXJjbGUoXHJcbiAgICAgIGRhdGEuZHJhd2FibGUuYnJ1c2hlc1tzaGFwZS5icnVzaF0sXHJcbiAgICAgIG9yaWVudChrZXkycG9zKHNoYXBlLm9yaWcpLCBkYXRhLm9yaWVudGF0aW9uKSxcclxuICAgICAgY3VycmVudCwgYm91bmRzKTtcclxuICB9O1xyXG59XHJcblxyXG5tb2R1bGUuZXhwb3J0cyA9IGZ1bmN0aW9uKGN0cmwpIHtcclxuICBpZiAoIWN0cmwuZGF0YS5ib3VuZHMpIHJldHVybjtcclxuICB2YXIgZCA9IGN0cmwuZGF0YS5kcmF3YWJsZTtcclxuICB2YXIgYWxsU2hhcGVzID0gZC5zaGFwZXMuY29uY2F0KGQuYXV0b1NoYXBlcyk7XHJcbiAgaWYgKCFhbGxTaGFwZXMubGVuZ3RoICYmICFkLmN1cnJlbnQub3JpZykgcmV0dXJuO1xyXG4gIHZhciBib3VuZHMgPSBjdHJsLmRhdGEuYm91bmRzKCk7XHJcbiAgaWYgKGJvdW5kcy53aWR0aCAhPT0gYm91bmRzLmhlaWdodCkgcmV0dXJuO1xyXG4gIHZhciB1c2VkQnJ1c2hlcyA9IE9iamVjdC5rZXlzKGQuYnJ1c2hlcykuZmlsdGVyKGZ1bmN0aW9uKG5hbWUpIHtcclxuICAgIHJldHVybiAoZC5jdXJyZW50ICYmIGQuY3VycmVudC5kZXN0ICYmIGQuY3VycmVudC5icnVzaCA9PT0gbmFtZSkgfHwgYWxsU2hhcGVzLmZpbHRlcihmdW5jdGlvbihzKSB7XHJcbiAgICAgIHJldHVybiBzLmRlc3QgJiYgcy5icnVzaCA9PT0gbmFtZTtcclxuICAgIH0pLmxlbmd0aDtcclxuICB9KS5tYXAoZnVuY3Rpb24obmFtZSkge1xyXG4gICAgcmV0dXJuIGQuYnJ1c2hlc1tuYW1lXTtcclxuICB9KTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiAnc3ZnJyxcclxuICAgIGF0dHJzOiB7XHJcbiAgICAgIGtleTogJ3N2ZydcclxuICAgIH0sXHJcbiAgICBjaGlsZHJlbjogW1xyXG4gICAgICBkZWZzKHVzZWRCcnVzaGVzKSxcclxuICAgICAgYWxsU2hhcGVzLm1hcChyZW5kZXJTaGFwZShjdHJsLmRhdGEsIGZhbHNlLCBib3VuZHMpKSxcclxuICAgICAgcmVuZGVyU2hhcGUoY3RybC5kYXRhLCB0cnVlLCBib3VuZHMpKGQuY3VycmVudClcclxuICAgIF1cclxuICB9O1xyXG59XHJcbiIsInZhciBmaWxlcyA9IFwiYWJjZGVmZ2hcIi5zcGxpdCgnJyk7XHJcbnZhciByYW5rcyA9IFsxLCAyLCAzLCA0LCA1LCA2LCA3LCA4XTtcclxudmFyIGludlJhbmtzID0gWzgsIDcsIDYsIDUsIDQsIDMsIDIsIDFdO1xyXG52YXIgZmlsZU51bWJlcnMgPSB7XHJcbiAgYTogMSxcclxuICBiOiAyLFxyXG4gIGM6IDMsXHJcbiAgZDogNCxcclxuICBlOiA1LFxyXG4gIGY6IDYsXHJcbiAgZzogNyxcclxuICBoOiA4XHJcbn07XHJcblxyXG5mdW5jdGlvbiBwb3Mya2V5KHBvcykge1xyXG4gIHJldHVybiBmaWxlc1twb3NbMF0gLSAxXSArIHBvc1sxXTtcclxufVxyXG5cclxuZnVuY3Rpb24ga2V5MnBvcyhwb3MpIHtcclxuICByZXR1cm4gW2ZpbGVOdW1iZXJzW3Bvc1swXV0sIHBhcnNlSW50KHBvc1sxXSldO1xyXG59XHJcblxyXG5mdW5jdGlvbiBpbnZlcnRLZXkoa2V5KSB7XHJcbiAgcmV0dXJuIGZpbGVzWzggLSBmaWxlTnVtYmVyc1trZXlbMF1dXSArICg5IC0gcGFyc2VJbnQoa2V5WzFdKSk7XHJcbn1cclxuXHJcbnZhciBhbGxQb3MgPSAoZnVuY3Rpb24oKSB7XHJcbiAgdmFyIHBzID0gW107XHJcbiAgaW52UmFua3MuZm9yRWFjaChmdW5jdGlvbih5KSB7XHJcbiAgICByYW5rcy5mb3JFYWNoKGZ1bmN0aW9uKHgpIHtcclxuICAgICAgcHMucHVzaChbeCwgeV0pO1xyXG4gICAgfSk7XHJcbiAgfSk7XHJcbiAgcmV0dXJuIHBzO1xyXG59KSgpO1xyXG52YXIgYWxsS2V5cyA9IGFsbFBvcy5tYXAocG9zMmtleSk7XHJcbnZhciBpbnZLZXlzID0gYWxsS2V5cy5zbGljZSgwKS5yZXZlcnNlKCk7XHJcblxyXG5mdW5jdGlvbiBjbGFzc1NldChjbGFzc2VzKSB7XHJcbiAgdmFyIGFyciA9IFtdO1xyXG4gIGZvciAodmFyIGkgaW4gY2xhc3Nlcykge1xyXG4gICAgaWYgKGNsYXNzZXNbaV0pIGFyci5wdXNoKGkpO1xyXG4gIH1cclxuICByZXR1cm4gYXJyLmpvaW4oJyAnKTtcclxufVxyXG5cclxuZnVuY3Rpb24gb3Bwb3NpdGUoY29sb3IpIHtcclxuICByZXR1cm4gY29sb3IgPT09ICd3aGl0ZScgPyAnYmxhY2snIDogJ3doaXRlJztcclxufVxyXG5cclxuZnVuY3Rpb24gY29udGFpbnNYKHhzLCB4KSB7XHJcbiAgcmV0dXJuIHhzICYmIHhzLmluZGV4T2YoeCkgIT09IC0xO1xyXG59XHJcblxyXG5mdW5jdGlvbiBkaXN0YW5jZShwb3MxLCBwb3MyKSB7XHJcbiAgcmV0dXJuIE1hdGguc3FydChNYXRoLnBvdyhwb3MxWzBdIC0gcG9zMlswXSwgMikgKyBNYXRoLnBvdyhwb3MxWzFdIC0gcG9zMlsxXSwgMikpO1xyXG59XHJcblxyXG4vLyB0aGlzIG11c3QgYmUgY2FjaGVkIGJlY2F1c2Ugb2YgdGhlIGFjY2VzcyB0byBkb2N1bWVudC5ib2R5LnN0eWxlXHJcbnZhciBjYWNoZWRUcmFuc2Zvcm1Qcm9wO1xyXG5cclxuZnVuY3Rpb24gY29tcHV0ZVRyYW5zZm9ybVByb3AoKSB7XHJcbiAgcmV0dXJuICd0cmFuc2Zvcm0nIGluIGRvY3VtZW50LmJvZHkuc3R5bGUgP1xyXG4gICAgJ3RyYW5zZm9ybScgOiAnd2Via2l0VHJhbnNmb3JtJyBpbiBkb2N1bWVudC5ib2R5LnN0eWxlID9cclxuICAgICd3ZWJraXRUcmFuc2Zvcm0nIDogJ21velRyYW5zZm9ybScgaW4gZG9jdW1lbnQuYm9keS5zdHlsZSA/XHJcbiAgICAnbW96VHJhbnNmb3JtJyA6ICdvVHJhbnNmb3JtJyBpbiBkb2N1bWVudC5ib2R5LnN0eWxlID9cclxuICAgICdvVHJhbnNmb3JtJyA6ICdtc1RyYW5zZm9ybSc7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHRyYW5zZm9ybVByb3AoKSB7XHJcbiAgaWYgKCFjYWNoZWRUcmFuc2Zvcm1Qcm9wKSBjYWNoZWRUcmFuc2Zvcm1Qcm9wID0gY29tcHV0ZVRyYW5zZm9ybVByb3AoKTtcclxuICByZXR1cm4gY2FjaGVkVHJhbnNmb3JtUHJvcDtcclxufVxyXG5cclxudmFyIGNhY2hlZElzVHJpZGVudCA9IG51bGw7XHJcblxyXG5mdW5jdGlvbiBpc1RyaWRlbnQoKSB7XHJcbiAgaWYgKGNhY2hlZElzVHJpZGVudCA9PT0gbnVsbClcclxuICAgIGNhY2hlZElzVHJpZGVudCA9IHdpbmRvdy5uYXZpZ2F0b3IudXNlckFnZW50LmluZGV4T2YoJ1RyaWRlbnQvJykgPiAtMTtcclxuICByZXR1cm4gY2FjaGVkSXNUcmlkZW50O1xyXG59XHJcblxyXG5mdW5jdGlvbiB0cmFuc2xhdGUocG9zKSB7XHJcbiAgcmV0dXJuICd0cmFuc2xhdGUoJyArIHBvc1swXSArICdweCwnICsgcG9zWzFdICsgJ3B4KSc7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGV2ZW50UG9zaXRpb24oZSkge1xyXG4gIGlmIChlLmNsaWVudFggfHwgZS5jbGllbnRYID09PSAwKSByZXR1cm4gW2UuY2xpZW50WCwgZS5jbGllbnRZXTtcclxuICBpZiAoZS50b3VjaGVzICYmIGUudGFyZ2V0VG91Y2hlc1swXSkgcmV0dXJuIFtlLnRhcmdldFRvdWNoZXNbMF0uY2xpZW50WCwgZS50YXJnZXRUb3VjaGVzWzBdLmNsaWVudFldO1xyXG59XHJcblxyXG5mdW5jdGlvbiBwYXJ0aWFsQXBwbHkoZm4sIGFyZ3MpIHtcclxuICByZXR1cm4gZm4uYmluZC5hcHBseShmbiwgW251bGxdLmNvbmNhdChhcmdzKSk7XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHBhcnRpYWwoKSB7XHJcbiAgcmV0dXJuIHBhcnRpYWxBcHBseShhcmd1bWVudHNbMF0sIEFycmF5LnByb3RvdHlwZS5zbGljZS5jYWxsKGFyZ3VtZW50cywgMSkpO1xyXG59XHJcblxyXG5mdW5jdGlvbiBpc1JpZ2h0QnV0dG9uKGUpIHtcclxuICByZXR1cm4gZS5idXR0b25zID09PSAyIHx8IGUuYnV0dG9uID09PSAyO1xyXG59XHJcblxyXG5mdW5jdGlvbiBtZW1vKGYpIHtcclxuICB2YXIgdiwgcmV0ID0gZnVuY3Rpb24oKSB7XHJcbiAgICBpZiAodiA9PT0gdW5kZWZpbmVkKSB2ID0gZigpO1xyXG4gICAgcmV0dXJuIHY7XHJcbiAgfTtcclxuICByZXQuY2xlYXIgPSBmdW5jdGlvbigpIHtcclxuICAgIHYgPSB1bmRlZmluZWQ7XHJcbiAgfVxyXG4gIHJldHVybiByZXQ7XHJcbn1cclxuXHJcbm1vZHVsZS5leHBvcnRzID0ge1xyXG4gIGZpbGVzOiBmaWxlcyxcclxuICByYW5rczogcmFua3MsXHJcbiAgaW52UmFua3M6IGludlJhbmtzLFxyXG4gIGFsbFBvczogYWxsUG9zLFxyXG4gIGFsbEtleXM6IGFsbEtleXMsXHJcbiAgaW52S2V5czogaW52S2V5cyxcclxuICBwb3Mya2V5OiBwb3Mya2V5LFxyXG4gIGtleTJwb3M6IGtleTJwb3MsXHJcbiAgaW52ZXJ0S2V5OiBpbnZlcnRLZXksXHJcbiAgY2xhc3NTZXQ6IGNsYXNzU2V0LFxyXG4gIG9wcG9zaXRlOiBvcHBvc2l0ZSxcclxuICB0cmFuc2xhdGU6IHRyYW5zbGF0ZSxcclxuICBjb250YWluc1g6IGNvbnRhaW5zWCxcclxuICBkaXN0YW5jZTogZGlzdGFuY2UsXHJcbiAgZXZlbnRQb3NpdGlvbjogZXZlbnRQb3NpdGlvbixcclxuICBwYXJ0aWFsQXBwbHk6IHBhcnRpYWxBcHBseSxcclxuICBwYXJ0aWFsOiBwYXJ0aWFsLFxyXG4gIHRyYW5zZm9ybVByb3A6IHRyYW5zZm9ybVByb3AsXHJcbiAgaXNUcmlkZW50OiBpc1RyaWRlbnQsXHJcbiAgcmVxdWVzdEFuaW1hdGlvbkZyYW1lOiAod2luZG93LnJlcXVlc3RBbmltYXRpb25GcmFtZSB8fCB3aW5kb3cuc2V0VGltZW91dCkuYmluZCh3aW5kb3cpLFxyXG4gIGlzUmlnaHRCdXR0b246IGlzUmlnaHRCdXR0b24sXHJcbiAgbWVtbzogbWVtb1xyXG59O1xyXG4iLCJ2YXIgZHJhZyA9IHJlcXVpcmUoJy4vZHJhZycpO1xyXG52YXIgZHJhdyA9IHJlcXVpcmUoJy4vZHJhdycpO1xyXG52YXIgdXRpbCA9IHJlcXVpcmUoJy4vdXRpbCcpO1xyXG52YXIgc3ZnID0gcmVxdWlyZSgnLi9zdmcnKTtcclxudmFyIG1ha2VDb29yZHMgPSByZXF1aXJlKCcuL2Nvb3JkcycpO1xyXG52YXIgbSA9IHJlcXVpcmUoJ21pdGhyaWwnKTtcclxuXHJcbnZhciBwaWVjZVRhZyA9ICdwaWVjZSc7XHJcbnZhciBzcXVhcmVUYWcgPSAnc3F1YXJlJztcclxuXHJcbmZ1bmN0aW9uIHBpZWNlQ2xhc3MocCkge1xyXG4gIHJldHVybiBwLnJvbGUgKyAnICcgKyBwLmNvbG9yO1xyXG59XHJcblxyXG5mdW5jdGlvbiByZW5kZXJQaWVjZShkLCBrZXksIGN0eCkge1xyXG4gIHZhciBhdHRycyA9IHtcclxuICAgIGtleTogJ3AnICsga2V5LFxyXG4gICAgc3R5bGU6IHt9LFxyXG4gICAgY2xhc3M6IHBpZWNlQ2xhc3MoZC5waWVjZXNba2V5XSlcclxuICB9O1xyXG4gIHZhciB0cmFuc2xhdGUgPSBwb3NUb1RyYW5zbGF0ZSh1dGlsLmtleTJwb3Moa2V5KSwgY3R4KTtcclxuICB2YXIgZHJhZ2dhYmxlID0gZC5kcmFnZ2FibGUuY3VycmVudDtcclxuICBpZiAoZHJhZ2dhYmxlLm9yaWcgPT09IGtleSAmJiBkcmFnZ2FibGUuc3RhcnRlZCkge1xyXG4gICAgdHJhbnNsYXRlWzBdICs9IGRyYWdnYWJsZS5wb3NbMF0gKyBkcmFnZ2FibGUuZGVjWzBdO1xyXG4gICAgdHJhbnNsYXRlWzFdICs9IGRyYWdnYWJsZS5wb3NbMV0gKyBkcmFnZ2FibGUuZGVjWzFdO1xyXG4gICAgYXR0cnMuY2xhc3MgKz0gJyBkcmFnZ2luZyc7XHJcbiAgfSBlbHNlIGlmIChkLmFuaW1hdGlvbi5jdXJyZW50LmFuaW1zKSB7XHJcbiAgICB2YXIgYW5pbWF0aW9uID0gZC5hbmltYXRpb24uY3VycmVudC5hbmltc1trZXldO1xyXG4gICAgaWYgKGFuaW1hdGlvbikge1xyXG4gICAgICB0cmFuc2xhdGVbMF0gKz0gYW5pbWF0aW9uWzFdWzBdO1xyXG4gICAgICB0cmFuc2xhdGVbMV0gKz0gYW5pbWF0aW9uWzFdWzFdO1xyXG4gICAgfVxyXG4gIH1cclxuICBhdHRycy5zdHlsZVtjdHgudHJhbnNmb3JtUHJvcF0gPSB1dGlsLnRyYW5zbGF0ZSh0cmFuc2xhdGUpO1xyXG4gIGlmIChkLnBpZWNlS2V5KSBhdHRyc1snZGF0YS1rZXknXSA9IGtleTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiBwaWVjZVRhZyxcclxuICAgIGF0dHJzOiBhdHRyc1xyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHJlbmRlclNxdWFyZShrZXksIGNsYXNzZXMsIGN0eCkge1xyXG4gIHZhciBhdHRycyA9IHtcclxuICAgIGtleTogJ3MnICsga2V5LFxyXG4gICAgY2xhc3M6IGNsYXNzZXMsXHJcbiAgICBzdHlsZToge31cclxuICB9O1xyXG4gIGF0dHJzLnN0eWxlW2N0eC50cmFuc2Zvcm1Qcm9wXSA9IHV0aWwudHJhbnNsYXRlKHBvc1RvVHJhbnNsYXRlKHV0aWwua2V5MnBvcyhrZXkpLCBjdHgpKTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiBzcXVhcmVUYWcsXHJcbiAgICBhdHRyczogYXR0cnNcclxuICB9O1xyXG59XHJcblxyXG5mdW5jdGlvbiBwb3NUb1RyYW5zbGF0ZShwb3MsIGN0eCkge1xyXG4gIHJldHVybiBbXHJcbiAgICAoY3R4LmFzV2hpdGUgPyBwb3NbMF0gLSAxIDogOCAtIHBvc1swXSkgKiBjdHguYm91bmRzLndpZHRoIC8gOCwgKGN0eC5hc1doaXRlID8gOCAtIHBvc1sxXSA6IHBvc1sxXSAtIDEpICogY3R4LmJvdW5kcy5oZWlnaHQgLyA4XHJcbiAgXTtcclxufVxyXG5cclxuZnVuY3Rpb24gcmVuZGVyR2hvc3Qoa2V5LCBwaWVjZSwgY3R4KSB7XHJcbiAgaWYgKCFwaWVjZSkgcmV0dXJuO1xyXG4gIHZhciBhdHRycyA9IHtcclxuICAgIGtleTogJ2cnICsga2V5LFxyXG4gICAgc3R5bGU6IHt9LFxyXG4gICAgY2xhc3M6IHBpZWNlQ2xhc3MocGllY2UpICsgJyBnaG9zdCdcclxuICB9O1xyXG4gIGF0dHJzLnN0eWxlW2N0eC50cmFuc2Zvcm1Qcm9wXSA9IHV0aWwudHJhbnNsYXRlKHBvc1RvVHJhbnNsYXRlKHV0aWwua2V5MnBvcyhrZXkpLCBjdHgpKTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiBwaWVjZVRhZyxcclxuICAgIGF0dHJzOiBhdHRyc1xyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHJlbmRlckZhZGluZyhjZmcsIGN0eCkge1xyXG4gIHZhciBhdHRycyA9IHtcclxuICAgIGtleTogJ2YnICsgY2ZnLnBpZWNlLmtleSxcclxuICAgIGNsYXNzOiAnZmFkaW5nICcgKyBwaWVjZUNsYXNzKGNmZy5waWVjZSksXHJcbiAgICBzdHlsZToge1xyXG4gICAgICBvcGFjaXR5OiBjZmcub3BhY2l0eVxyXG4gICAgfVxyXG4gIH07XHJcbiAgYXR0cnMuc3R5bGVbY3R4LnRyYW5zZm9ybVByb3BdID0gdXRpbC50cmFuc2xhdGUocG9zVG9UcmFuc2xhdGUoY2ZnLnBpZWNlLnBvcywgY3R4KSk7XHJcbiAgcmV0dXJuIHtcclxuICAgIHRhZzogcGllY2VUYWcsXHJcbiAgICBhdHRyczogYXR0cnNcclxuICB9O1xyXG59XHJcblxyXG5mdW5jdGlvbiBhZGRTcXVhcmUoc3F1YXJlcywga2V5LCBrbGFzcykge1xyXG4gIGlmIChzcXVhcmVzW2tleV0pIHNxdWFyZXNba2V5XS5wdXNoKGtsYXNzKTtcclxuICBlbHNlIHNxdWFyZXNba2V5XSA9IFtrbGFzc107XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHJlbmRlclNxdWFyZXMoY3RybCwgY3R4KSB7XHJcbiAgdmFyIGQgPSBjdHJsLmRhdGE7XHJcbiAgdmFyIHNxdWFyZXMgPSB7fTtcclxuICBpZiAoZC5sYXN0TW92ZSAmJiBkLmhpZ2hsaWdodC5sYXN0TW92ZSkgZC5sYXN0TW92ZS5mb3JFYWNoKGZ1bmN0aW9uKGspIHtcclxuICAgIGFkZFNxdWFyZShzcXVhcmVzLCBrLCAnbGFzdC1tb3ZlJyk7XHJcbiAgfSk7XHJcbiAgaWYgKGQuY2hlY2sgJiYgZC5oaWdobGlnaHQuY2hlY2spIGFkZFNxdWFyZShzcXVhcmVzLCBkLmNoZWNrLCAnY2hlY2snKTtcclxuICBpZiAoZC5zZWxlY3RlZCkge1xyXG4gICAgYWRkU3F1YXJlKHNxdWFyZXMsIGQuc2VsZWN0ZWQsICdzZWxlY3RlZCcpO1xyXG4gICAgdmFyIG92ZXIgPSBkLmRyYWdnYWJsZS5jdXJyZW50Lm92ZXI7XHJcbiAgICB2YXIgZGVzdHMgPSBkLm1vdmFibGUuZGVzdHNbZC5zZWxlY3RlZF07XHJcbiAgICBpZiAoZGVzdHMpIGRlc3RzLmZvckVhY2goZnVuY3Rpb24oaykge1xyXG4gICAgICBpZiAoayA9PT0gb3ZlcikgYWRkU3F1YXJlKHNxdWFyZXMsIGssICdtb3ZlLWRlc3QgZHJhZy1vdmVyJyk7XHJcbiAgICAgIGVsc2UgaWYgKGQubW92YWJsZS5zaG93RGVzdHMpIGFkZFNxdWFyZShzcXVhcmVzLCBrLCAnbW92ZS1kZXN0JyArIChkLnBpZWNlc1trXSA/ICcgb2MnIDogJycpKTtcclxuICAgIH0pO1xyXG4gICAgdmFyIHBEZXN0cyA9IGQucHJlbW92YWJsZS5kZXN0cztcclxuICAgIGlmIChwRGVzdHMpIHBEZXN0cy5mb3JFYWNoKGZ1bmN0aW9uKGspIHtcclxuICAgICAgaWYgKGsgPT09IG92ZXIpIGFkZFNxdWFyZShzcXVhcmVzLCBrLCAncHJlbW92ZS1kZXN0IGRyYWctb3ZlcicpO1xyXG4gICAgICBlbHNlIGlmIChkLm1vdmFibGUuc2hvd0Rlc3RzKSBhZGRTcXVhcmUoc3F1YXJlcywgaywgJ3ByZW1vdmUtZGVzdCcgKyAoZC5waWVjZXNba10gPyAnIG9jJyA6ICcnKSk7XHJcbiAgICB9KTtcclxuICB9XHJcbiAgdmFyIHByZW1vdmUgPSBkLnByZW1vdmFibGUuY3VycmVudDtcclxuICBpZiAocHJlbW92ZSkgcHJlbW92ZS5mb3JFYWNoKGZ1bmN0aW9uKGspIHtcclxuICAgIGFkZFNxdWFyZShzcXVhcmVzLCBrLCAnY3VycmVudC1wcmVtb3ZlJyk7XHJcbiAgfSk7XHJcbiAgZWxzZSBpZiAoZC5wcmVkcm9wcGFibGUuY3VycmVudC5rZXkpXHJcbiAgICBhZGRTcXVhcmUoc3F1YXJlcywgZC5wcmVkcm9wcGFibGUuY3VycmVudC5rZXksICdjdXJyZW50LXByZW1vdmUnKTtcclxuXHJcbiAgaWYgKGN0cmwudm0uZXhwbG9kaW5nKSBjdHJsLnZtLmV4cGxvZGluZy5rZXlzLmZvckVhY2goZnVuY3Rpb24oaykge1xyXG4gICAgYWRkU3F1YXJlKHNxdWFyZXMsIGssICdleHBsb2RpbmcnICsgY3RybC52bS5leHBsb2Rpbmcuc3RhZ2UpO1xyXG4gIH0pO1xyXG5cclxuICB2YXIgZG9tID0gW107XHJcbiAgaWYgKGQuaXRlbXMpIHtcclxuICAgIGZvciAodmFyIGkgPSAwOyBpIDwgNjQ7IGkrKykge1xyXG4gICAgICB2YXIga2V5ID0gdXRpbC5hbGxLZXlzW2ldO1xyXG4gICAgICB2YXIgc3F1YXJlID0gc3F1YXJlc1trZXldO1xyXG4gICAgICB2YXIgaXRlbSA9IGQuaXRlbXMucmVuZGVyKHV0aWwua2V5MnBvcyhrZXkpLCBrZXkpO1xyXG4gICAgICBpZiAoc3F1YXJlIHx8IGl0ZW0pIHtcclxuICAgICAgICB2YXIgc3EgPSByZW5kZXJTcXVhcmUoa2V5LCBzcXVhcmUgPyBzcXVhcmUuam9pbignICcpICsgKGl0ZW0gPyAnIGhhcy1pdGVtJyA6ICcnKSA6ICdoYXMtaXRlbScsIGN0eCk7XHJcbiAgICAgICAgaWYgKGl0ZW0pIHNxLmNoaWxkcmVuID0gW2l0ZW1dO1xyXG4gICAgICAgIGRvbS5wdXNoKHNxKTtcclxuICAgICAgfVxyXG4gICAgfVxyXG4gIH0gZWxzZSB7XHJcbiAgICBmb3IgKHZhciBrZXkgaW4gc3F1YXJlcylcclxuICAgICAgZG9tLnB1c2gocmVuZGVyU3F1YXJlKGtleSwgc3F1YXJlc1trZXldLmpvaW4oJyAnKSwgY3R4KSk7XHJcbiAgfVxyXG4gIHJldHVybiBkb207XHJcbn1cclxuXHJcbmZ1bmN0aW9uIHJlbmRlckNvbnRlbnQoY3RybCkge1xyXG4gIHZhciBkID0gY3RybC5kYXRhO1xyXG4gIGlmICghZC5ib3VuZHMpIHJldHVybjtcclxuICB2YXIgY3R4ID0ge1xyXG4gICAgYXNXaGl0ZTogZC5vcmllbnRhdGlvbiA9PT0gJ3doaXRlJyxcclxuICAgIGJvdW5kczogZC5ib3VuZHMoKSxcclxuICAgIHRyYW5zZm9ybVByb3A6IHV0aWwudHJhbnNmb3JtUHJvcCgpXHJcbiAgfTtcclxuICB2YXIgY2hpbGRyZW4gPSByZW5kZXJTcXVhcmVzKGN0cmwsIGN0eCk7XHJcbiAgaWYgKGQuYW5pbWF0aW9uLmN1cnJlbnQuZmFkaW5ncylcclxuICAgIGQuYW5pbWF0aW9uLmN1cnJlbnQuZmFkaW5ncy5mb3JFYWNoKGZ1bmN0aW9uKHApIHtcclxuICAgICAgY2hpbGRyZW4ucHVzaChyZW5kZXJGYWRpbmcocCwgY3R4KSk7XHJcbiAgICB9KTtcclxuXHJcbiAgLy8gbXVzdCBpbnNlcnQgcGllY2VzIGluIHRoZSByaWdodCBvcmRlclxyXG4gIC8vIGZvciAzRCB0byBkaXNwbGF5IGNvcnJlY3RseVxyXG4gIHZhciBrZXlzID0gY3R4LmFzV2hpdGUgPyB1dGlsLmFsbEtleXMgOiB1dGlsLmludktleXM7XHJcbiAgaWYgKGQuaXRlbXMpXHJcbiAgICBmb3IgKHZhciBpID0gMDsgaSA8IDY0OyBpKyspIHtcclxuICAgICAgaWYgKGQucGllY2VzW2tleXNbaV1dICYmICFkLml0ZW1zLnJlbmRlcih1dGlsLmtleTJwb3Moa2V5c1tpXSksIGtleXNbaV0pKVxyXG4gICAgICAgIGNoaWxkcmVuLnB1c2gocmVuZGVyUGllY2UoZCwga2V5c1tpXSwgY3R4KSk7XHJcbiAgICB9IGVsc2VcclxuICAgICAgZm9yICh2YXIgaSA9IDA7IGkgPCA2NDsgaSsrKSB7XHJcbiAgICAgICAgaWYgKGQucGllY2VzW2tleXNbaV1dKSBjaGlsZHJlbi5wdXNoKHJlbmRlclBpZWNlKGQsIGtleXNbaV0sIGN0eCkpO1xyXG4gICAgICB9XHJcblxyXG4gIGlmIChkLmRyYWdnYWJsZS5zaG93R2hvc3QpIHtcclxuICAgIHZhciBkcmFnT3JpZyA9IGQuZHJhZ2dhYmxlLmN1cnJlbnQub3JpZztcclxuICAgIGlmIChkcmFnT3JpZyAmJiAhZC5kcmFnZ2FibGUuY3VycmVudC5uZXdQaWVjZSlcclxuICAgICAgY2hpbGRyZW4ucHVzaChyZW5kZXJHaG9zdChkcmFnT3JpZywgZC5waWVjZXNbZHJhZ09yaWddLCBjdHgpKTtcclxuICB9XHJcbiAgaWYgKGQuZHJhd2FibGUuZW5hYmxlZCkgY2hpbGRyZW4ucHVzaChzdmcoY3RybCkpO1xyXG4gIHJldHVybiBjaGlsZHJlbjtcclxufVxyXG5cclxuZnVuY3Rpb24gc3RhcnREcmFnT3JEcmF3KGQpIHtcclxuICByZXR1cm4gZnVuY3Rpb24oZSkge1xyXG4gICAgaWYgKHV0aWwuaXNSaWdodEJ1dHRvbihlKSAmJiBkLmRyYWdnYWJsZS5jdXJyZW50Lm9yaWcpIHtcclxuICAgICAgaWYgKGQuZHJhZ2dhYmxlLmN1cnJlbnQubmV3UGllY2UpIGRlbGV0ZSBkLnBpZWNlc1tkLmRyYWdnYWJsZS5jdXJyZW50Lm9yaWddO1xyXG4gICAgICBkLmRyYWdnYWJsZS5jdXJyZW50ID0ge31cclxuICAgICAgZC5zZWxlY3RlZCA9IG51bGw7XHJcbiAgICB9IGVsc2UgaWYgKChlLnNoaWZ0S2V5IHx8IHV0aWwuaXNSaWdodEJ1dHRvbihlKSkgJiYgZC5kcmF3YWJsZS5lbmFibGVkKSBkcmF3LnN0YXJ0KGQsIGUpO1xyXG4gICAgZWxzZSBkcmFnLnN0YXJ0KGQsIGUpO1xyXG4gIH07XHJcbn1cclxuXHJcbmZ1bmN0aW9uIGRyYWdPckRyYXcoZCwgd2l0aERyYWcsIHdpdGhEcmF3KSB7XHJcbiAgcmV0dXJuIGZ1bmN0aW9uKGUpIHtcclxuICAgIGlmICgoZS5zaGlmdEtleSB8fCB1dGlsLmlzUmlnaHRCdXR0b24oZSkpICYmIGQuZHJhd2FibGUuZW5hYmxlZCkgd2l0aERyYXcoZCwgZSk7XHJcbiAgICBlbHNlIGlmICghZC52aWV3T25seSkgd2l0aERyYWcoZCwgZSk7XHJcbiAgfTtcclxufVxyXG5cclxuZnVuY3Rpb24gYmluZEV2ZW50cyhjdHJsLCBlbCwgY29udGV4dCkge1xyXG4gIHZhciBkID0gY3RybC5kYXRhO1xyXG4gIHZhciBvbnN0YXJ0ID0gc3RhcnREcmFnT3JEcmF3KGQpO1xyXG4gIHZhciBvbm1vdmUgPSBkcmFnT3JEcmF3KGQsIGRyYWcubW92ZSwgZHJhdy5tb3ZlKTtcclxuICB2YXIgb25lbmQgPSBkcmFnT3JEcmF3KGQsIGRyYWcuZW5kLCBkcmF3LmVuZCk7XHJcbiAgdmFyIHN0YXJ0RXZlbnRzID0gWyd0b3VjaHN0YXJ0JywgJ21vdXNlZG93biddO1xyXG4gIHZhciBtb3ZlRXZlbnRzID0gWyd0b3VjaG1vdmUnLCAnbW91c2Vtb3ZlJ107XHJcbiAgdmFyIGVuZEV2ZW50cyA9IFsndG91Y2hlbmQnLCAnbW91c2V1cCddO1xyXG4gIHN0YXJ0RXZlbnRzLmZvckVhY2goZnVuY3Rpb24oZXYpIHtcclxuICAgIGVsLmFkZEV2ZW50TGlzdGVuZXIoZXYsIG9uc3RhcnQpO1xyXG4gIH0pO1xyXG4gIG1vdmVFdmVudHMuZm9yRWFjaChmdW5jdGlvbihldikge1xyXG4gICAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihldiwgb25tb3ZlKTtcclxuICB9KTtcclxuICBlbmRFdmVudHMuZm9yRWFjaChmdW5jdGlvbihldikge1xyXG4gICAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihldiwgb25lbmQpO1xyXG4gIH0pO1xyXG4gIGNvbnRleHQub251bmxvYWQgPSBmdW5jdGlvbigpIHtcclxuICAgIHN0YXJ0RXZlbnRzLmZvckVhY2goZnVuY3Rpb24oZXYpIHtcclxuICAgICAgZWwucmVtb3ZlRXZlbnRMaXN0ZW5lcihldiwgb25zdGFydCk7XHJcbiAgICB9KTtcclxuICAgIG1vdmVFdmVudHMuZm9yRWFjaChmdW5jdGlvbihldikge1xyXG4gICAgICBkb2N1bWVudC5yZW1vdmVFdmVudExpc3RlbmVyKGV2LCBvbm1vdmUpO1xyXG4gICAgfSk7XHJcbiAgICBlbmRFdmVudHMuZm9yRWFjaChmdW5jdGlvbihldikge1xyXG4gICAgICBkb2N1bWVudC5yZW1vdmVFdmVudExpc3RlbmVyKGV2LCBvbmVuZCk7XHJcbiAgICB9KTtcclxuICB9O1xyXG59XHJcblxyXG5mdW5jdGlvbiByZW5kZXJCb2FyZChjdHJsKSB7XHJcbiAgdmFyIGQgPSBjdHJsLmRhdGE7XHJcbiAgcmV0dXJuIHtcclxuICAgIHRhZzogJ2RpdicsXHJcbiAgICBhdHRyczoge1xyXG4gICAgICBjbGFzczogJ2NnLWJvYXJkIG9yaWVudGF0aW9uLScgKyBkLm9yaWVudGF0aW9uLFxyXG4gICAgICBjb25maWc6IGZ1bmN0aW9uKGVsLCBpc1VwZGF0ZSwgY29udGV4dCkge1xyXG4gICAgICAgIGlmIChpc1VwZGF0ZSkgcmV0dXJuO1xyXG4gICAgICAgIGlmICghZC52aWV3T25seSB8fCBkLmRyYXdhYmxlLmVuYWJsZWQpXHJcbiAgICAgICAgICBiaW5kRXZlbnRzKGN0cmwsIGVsLCBjb250ZXh0KTtcclxuICAgICAgICAvLyB0aGlzIGZ1bmN0aW9uIG9ubHkgcmVwYWludHMgdGhlIGJvYXJkIGl0c2VsZi5cclxuICAgICAgICAvLyBpdCdzIGNhbGxlZCB3aGVuIGRyYWdnaW5nIG9yIGFuaW1hdGluZyBwaWVjZXMsXHJcbiAgICAgICAgLy8gdG8gcHJldmVudCB0aGUgZnVsbCBhcHBsaWNhdGlvbiBlbWJlZGRpbmcgY2hlc3Nncm91bmRcclxuICAgICAgICAvLyByZW5kZXJpbmcgb24gZXZlcnkgYW5pbWF0aW9uIGZyYW1lXHJcbiAgICAgICAgZC5yZW5kZXIgPSBmdW5jdGlvbigpIHtcclxuICAgICAgICAgIG0ucmVuZGVyKGVsLCByZW5kZXJDb250ZW50KGN0cmwpKTtcclxuICAgICAgICB9O1xyXG4gICAgICAgIGQucmVuZGVyUkFGID0gZnVuY3Rpb24oKSB7XHJcbiAgICAgICAgICB1dGlsLnJlcXVlc3RBbmltYXRpb25GcmFtZShkLnJlbmRlcik7XHJcbiAgICAgICAgfTtcclxuICAgICAgICBkLmJvdW5kcyA9IHV0aWwubWVtbyhlbC5nZXRCb3VuZGluZ0NsaWVudFJlY3QuYmluZChlbCkpO1xyXG4gICAgICAgIGQuZWxlbWVudCA9IGVsO1xyXG4gICAgICAgIGQucmVuZGVyKCk7XHJcbiAgICAgIH1cclxuICAgIH0sXHJcbiAgICBjaGlsZHJlbjogW11cclxuICB9O1xyXG59XHJcblxyXG5tb2R1bGUuZXhwb3J0cyA9IGZ1bmN0aW9uKGN0cmwpIHtcclxuICB2YXIgZCA9IGN0cmwuZGF0YTtcclxuICByZXR1cm4ge1xyXG4gICAgdGFnOiAnZGl2JyxcclxuICAgIGF0dHJzOiB7XHJcbiAgICAgIGNvbmZpZzogZnVuY3Rpb24oZWwsIGlzVXBkYXRlLCBjdHgpIHtcclxuICAgICAgICBpZiAoaXNVcGRhdGUpIHtcclxuICAgICAgICAgIGlmIChjdHguY29vcmRzKSBjdHguY29vcmRzKGQub3JpZW50YXRpb24pO1xyXG4gICAgICAgICAgcmV0dXJuO1xyXG4gICAgICAgIH1cclxuICAgICAgICBpZiAoZC5jb29yZGluYXRlcykgY3R4LmNvb3JkcyA9IG1ha2VDb29yZHMoY3RybC5nZXRPcmllbnRhdGlvbigpLCBlbCk7XHJcbiAgICAgICAgZWwuYWRkRXZlbnRMaXN0ZW5lcignY29udGV4dG1lbnUnLCBmdW5jdGlvbihlKSB7XHJcbiAgICAgICAgICBpZiAoZC5kaXNhYmxlQ29udGV4dE1lbnUgfHwgZC5kcmF3YWJsZS5lbmFibGVkKSB7XHJcbiAgICAgICAgICAgIGUucHJldmVudERlZmF1bHQoKTtcclxuICAgICAgICAgICAgcmV0dXJuIGZhbHNlO1xyXG4gICAgICAgICAgfVxyXG4gICAgICAgIH0pO1xyXG4gICAgICAgIGlmIChkLnJlc2l6YWJsZSlcclxuICAgICAgICAgIGRvY3VtZW50LmJvZHkuYWRkRXZlbnRMaXN0ZW5lcignY2hlc3Nncm91bmQucmVzaXplJywgZnVuY3Rpb24oZSkge1xyXG4gICAgICAgICAgICBkLmJvdW5kcy5jbGVhcigpO1xyXG4gICAgICAgICAgICBkLnJlbmRlcigpO1xyXG4gICAgICAgICAgfSwgZmFsc2UpO1xyXG4gICAgICAgIFsnb25zY3JvbGwnLCAnb25yZXNpemUnXS5mb3JFYWNoKGZ1bmN0aW9uKG4pIHtcclxuICAgICAgICAgIHZhciBwcmV2ID0gd2luZG93W25dO1xyXG4gICAgICAgICAgd2luZG93W25dID0gZnVuY3Rpb24oKSB7XHJcbiAgICAgICAgICAgIHByZXYgJiYgcHJldigpO1xyXG4gICAgICAgICAgICBkLmJvdW5kcy5jbGVhcigpO1xyXG4gICAgICAgICAgfTtcclxuICAgICAgICB9KTtcclxuICAgICAgfSxcclxuICAgICAgY2xhc3M6IFtcclxuICAgICAgICAnY2ctYm9hcmQtd3JhcCcsXHJcbiAgICAgICAgZC52aWV3T25seSA/ICd2aWV3LW9ubHknIDogJ21hbmlwdWxhYmxlJ1xyXG4gICAgICBdLmpvaW4oJyAnKVxyXG4gICAgfSxcclxuICAgIGNoaWxkcmVuOiBbcmVuZGVyQm9hcmQoY3RybCldXHJcbiAgfTtcclxufTtcclxuIl19
